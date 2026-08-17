"""
P2S Dataset Builder: Deduplication, Stratified Oversampling,
Gentle Golden Reinforcement, and Token-Length Scanning.
"""
from __future__ import annotations
import json, os, random, re
from pathlib import Path
from typing import Any


def get_dedup_key(record: dict[str, Any]) -> str:
    """Extracts assistant response, strips command block, masks static emails & timestamps."""
    messages = record.get("messages", [])
    final_ans = messages[-1]["content"] if messages else record.get("mutated_command", "")
    cmd_match = re.search(r'```(?:bash|sh)?\n(.*?)\n```', final_ans, re.DOTALL)
    if cmd_match:
        cmd = cmd_match.group(1).strip()
        cmd = re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', '<email>', cmd)
        cmd = re.sub(r'\d{10,}', '<timestamp>', cmd)
        return cmd
    return final_ans.strip()


def scan_token_distribution(records: list[dict[str, Any]], max_seq_length: int = 24576):
    """Scans token lengths using a local fast tokenizer or word-approximation fallback."""
    print(f"\n[*] Scanning dataset token lengths (Target MAX_SEQ_LENGTH = {max_seq_length})...")

    tokenizer = None
    try:
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(
            "Qwen/Qwen2.5-7B-Instruct", trust_remote_code=False
        )
    except Exception:
        print("[!] Using word-count token approximation (1 word ≈ 1.3 tokens).")

    sample_lengths = []
    for rec in records:
        full_text = "\n".join(
            [f"{m['role']}: {m['content']}" for m in rec.get("messages", [])]
        )
        tokens = len(tokenizer.encode(full_text)) if tokenizer \
                 else int(len(full_text.split()) * 1.3)
        sample_lengths.append(tokens)

    n = len(sample_lengths)
    sl_sorted = sorted(sample_lengths)

    print("=" * 60)
    print("  CORPUS TOKEN LENGTH DISTRIBUTION")
    print("=" * 60)
    print(f"  Total Samples : {n}")
    print(f"  P50 Length    : {sl_sorted[n // 2]:,} tokens")
    print(f"  P90 Length    : {sl_sorted[int(n * 0.90)]:,} tokens")
    print(f"  P99 Length    : {sl_sorted[int(n * 0.99)]:,} tokens")
    print(f"  Max Length    : {sl_sorted[-1]:,} tokens")
    n_over = sum(1 for l in sample_lengths if l > max_seq_length)
    if n_over:
        print(f"  [WARN] {n_over} samples exceed MAX_SEQ_LENGTH={max_seq_length}")
    else:
        print(f"  [+] All samples fit within MAX_SEQ_LENGTH={max_seq_length}")
    print("=" * 60 + "\n")


def prepare_stratified_dataset(
    golden_file: str = "golden_dataset.jsonl",
    silver_file: str = "silver_dataset.jsonl",
    output_file: str = "final_training_dataset.jsonl",
    max_seq_length: int = 24576,
    seed: int = 3407
):
    """Ingests raw goldens/silvers, deduplicates, oversamples, and exports final corpus."""
    golden_raw, silver_raw = [], []
    for path, store in [(golden_file, golden_raw), (silver_file, silver_raw)]:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip(): continue
                    try: store.append(json.loads(line))
                    except json.JSONDecodeError: pass

    silver_records = list({get_dedup_key(r): r for r in silver_raw}.values())
    golden_records = list({get_dedup_key(r): r for r in golden_raw}.values())

    if not golden_records or not silver_records:
        raise FileNotFoundError(f"Missing or empty {golden_file} / {silver_file}")

    # Target ~4:1 Silver:Golden ratio
    multiplier = max(1, int((len(silver_records) / 4.0) / len(golden_records)))
    balanced_golden = golden_records * multiplier

    # Gentle Golden Reinforcement: second unshuffled copy appended so the final
    # gradient steps of every epoch see Golden exploit examples.
    all_records = silver_records + balanced_golden + golden_records
    random.seed(seed)
    random.shuffle(all_records)

    with open(output_file, "w", encoding="utf-8") as f:
        for rec in all_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"\n{'='*60}")
    print("  STRATIFIED CORPUS PREPARATION COMPLETED")
    print(f"{'='*60}")
    print(f" - Raw Silver Ingested    : {len(silver_raw)}")
    print(f" - Deduped Silver         : {len(silver_records)} "
          f"(Dropped {len(silver_raw)-len(silver_records)})")
    print(f" - Deduped Golden         : {len(golden_records)} "
          f"(x{multiplier} = {len(balanced_golden)})")
    print(f" - Final Target Ratio     : {len(silver_records)/len(balanced_golden):.2f} : 1")
    print(f" - Total Corpus Size      : {len(all_records)} samples")
    print(f" - Output Dataset File    : {output_file}")
    print(f"{'='*60}")

    scan_token_distribution(all_records, max_seq_length=max_seq_length)
