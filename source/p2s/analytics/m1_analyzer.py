"""
P2S Cumulative M1 Analyzer: Parses execution logs and JSONL records
to compute the true cumulative M1 syntax pass rate across multi-session runs.
"""
import os, re, json

def run_m1_analysis(backend_prefix: str = "openai",
                    log_file: str = None, meta_file: str = None):
    log_file = log_file or f"{backend_prefix}_execution_log.txt"
    golden_file = f"{backend_prefix}_golden_dataset.jsonl"
    silver_file = f"{backend_prefix}_silver_dataset.jsonl"
    meta_file = meta_file or f"{backend_prefix}_run_metadata.json"

    if not os.path.exists(log_file):
        print(f"[ERROR] Execution log file '{log_file}' not found."); return

    def count_jsonl(path):
        if not os.path.exists(path): return 0
        c = 0
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip(): c += 1
        return c

    golden_count = count_jsonl(golden_file)
    silver_count = count_jsonl(silver_file)
    total_api_responses = golden_count + silver_count

    with open(log_file, "r", encoding="utf-8") as f: content = f.read()

    cli_syntax_fails = len(re.findall(r'\[CLI EXEC FAIL\]|Execution Error:', content))
    empty_skips = len(re.findall(r'\[SKIP\] Empty command', content))
    refusals = len(re.findall(r'\[REFUSAL\] Model declined', content))
    intentional_omits = len(re.findall(r'Missing required options', content, re.IGNORECASE))
    arg_too_long = len(re.findall(r'argument list too long', content, re.IGNORECASE))

    m1_denominator = total_api_responses + cli_syntax_fails
    m1_rate = (total_api_responses / max(1, m1_denominator)) * 100

    print("=" * 60)
    print(f"  CUMULATIVE M1 ANALYSIS [{backend_prefix.upper()}]")
    print("=" * 60)
    print(f"  Golden Records on Disk  : {golden_count}")
    print(f"  Silver Records on Disk  : {silver_count}")
    print(f"  Total API Responses (ra): {total_api_responses}")
    print(f"  CLI Syntax Failures (sf): {cli_syntax_fails}")
    print(f"    ↳ Intentional Omission: {intentional_omits}")
    print(f"    ↳ Argument Too Long   : {arg_too_long}")
    print(f"  Empty Command Skips     : {empty_skips}")
    print(f"  Model Refusals          : {refusals}")
    print("-" * 60)
    print(f"  TRUE CUMULATIVE M1 PASS RATE : "
          f"{total_api_responses}/{m1_denominator} = {m1_rate:.2f}%")
    print("=" * 60)

    if os.path.exists(meta_file):
        with open(meta_file, "r", encoding="utf-8") as f: meta = json.load(f)
        meta["cumulative_global_m1"] = {
            "total_api_responses": total_api_responses,
            "total_cli_syntax_fails": cli_syntax_fails,
            "total_executed_attempts": m1_denominator,
            "true_m1_pass_rate": f"{m1_rate:.2f}%"
        }
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        print(f"  [UPDATED] Metadata file: {meta_file}")
