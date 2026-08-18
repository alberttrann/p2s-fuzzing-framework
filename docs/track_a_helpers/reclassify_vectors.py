#!/usr/bin/env python3
import json
import os
import sys
import re
import requests
import time

# ─── CONFIGURATION ───────────────────────────────────────────────────────────
BACKEND = sys.argv[1] if len(sys.argv) > 1 else "openai"

GOLDEN_FILE = f"{BACKEND}_golden_dataset.jsonl"
SILVER_FILE = f"{BACKEND}_silver_dataset.jsonl"
OUT_GOLDEN = f"{BACKEND}_golden_dataset_reclassified.jsonl"
OUT_SILVER = f"{BACKEND}_silver_dataset_reclassified.jsonl"

LOCAL_SLM_BASE_URL = "http://localhost:1234/v1"

# Strictly aligned with the P2S engine's _VECTOR_PATTERNS outputs
ALLOWED_CLASSES = [
    "Null-Byte", "Type Confusion", "Integer Boundary", "String Extremes",
    "SQLi", "XSS", "Encoding", "Mandatory Omission", "Parameter Conflict",
    "IDOR", "Mass Assignment", "BOLA/BFLA", "Business Flow", "Replay", 
    "Context Desync", "Premature Progression", "Unknown"
]

SYSTEM_PROMPT = """You are an expert cybersecurity classifier. 
Classify the following API fuzzing test case into EXACTLY ONE of the 16 categories based on the reasoning and the command.

1. Null-Byte
2. Type Confusion
3. Integer Boundary
4. String Extremes
5. SQLi
6. XSS
7. Encoding
8. Mandatory Omission
9. Parameter Conflict
10. IDOR
11. Mass Assignment
12. BOLA/BFLA
13. Business Flow
14. Replay
15. Context Desync
16. Premature Progression

OUTPUT FORMAT:
Output ONLY the exact name of the category from the list above. No numbers, no explanation, no markdown.
"""

def classify_with_slm(reasoning, command, raw_msg, attempt=1):
    if not reasoning and not command:
        prompt = f"Categorize this attack:\n{raw_msg}\n\nCategory Name:"
    else:
        prompt = f"Reasoning:\n{reasoning}\n\nCommand:\n{command}\n\nCategory Name:"
    
    payload = {
        "model": "local-model",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.0,
        "max_tokens": 24000 # Increased to allow reasoning models to finish their <think> blocks
    }
    
    try:
        resp = requests.post(f"{LOCAL_SLM_BASE_URL}/chat/completions", json=payload, timeout=800)
        resp.raise_for_status()
        
        message_data = resp.json()["choices"][0]["message"]
        raw_output = message_data.get("content", "").strip()
        
        if not raw_output and message_data.get("reasoning_content"):
            lines = [line.strip() for line in message_data["reasoning_content"].split('\n') if line.strip()]
            if lines: raw_output = lines[-1]
            
        out_lower = raw_output.lower()
        
        if "null" in out_lower and "byte" in out_lower: return "Null-Byte"
        if "type" in out_lower and "confusion" in out_lower: return "Type Confusion"
        if "integer" in out_lower or "boundar" in out_lower: return "Integer Boundary"
        if "extreme" in out_lower or "empty string" in out_lower: return "String Extremes"
        if "sql" in out_lower: return "SQLi"
        if "xss" in out_lower or "cross" in out_lower: return "XSS"
        if "encod" in out_lower: return "Encoding"
        if "omit" in out_lower or "mandatory" in out_lower: return "Mandatory Omission"
        if "conflict" in out_lower or "exclusive" in out_lower: return "Parameter Conflict"
        if "idor" in out_lower or "traversal" in out_lower: return "IDOR"
        if "mass" in out_lower and "assign" in out_lower: return "Mass Assignment"
        if "bola" in out_lower or "bfla" in out_lower: return "BOLA/BFLA"
        if "business flow" in out_lower or "bypass" in out_lower: return "Business Flow"
        if "replay" in out_lower or "idempoten" in out_lower: return "Replay"
        if "desync" in out_lower or "context" in out_lower: return "Context Desync"
        if "premature" in out_lower or "progression" in out_lower: return "Premature Progression"

        return f"Unknown (Raw SLM: {raw_output})"
        
    except Exception as e:
        if attempt < 3:
            time.sleep(1)
            return classify_with_slm(reasoning, command, raw_msg, attempt + 1)
        return f"Unknown (Error: {e})"

def process_file(in_file, out_file):
    if not os.path.exists(in_file):
        print(f"[SKIP] Input file not found: {in_file}")
        return

    print(f"\nProcessing {in_file} -> {out_file}")
    records = []
    with open(in_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))

    total = len(records)

    # ── Checkpoint & Resume Logic ─────────────────────────────────────────────
    already_processed = 0
    valid_lines = []
    if os.path.exists(out_file):
        with open(out_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        json.loads(line) # Validate line integrity
                        valid_lines.append(line)
                    except json.JSONDecodeError:
                        break # Stop at first corrupt/partial line from a crash
        already_processed = len(valid_lines)

    if already_processed >= total and total > 0:
        print(f"[SKIP] {out_file} is already fully processed ({already_processed}/{total} records).")
        return

    if already_processed > 0:
        print(f"[RESUME] Found {already_processed} existing records. Resuming from record {already_processed + 1}/{total}...")
        # Rewrite clean valid lines to fix any partial line from a crash
        with open(out_file, "w", encoding="utf-8") as f:
            f.writelines(valid_lines)
        file_mode = "a"
    else:
        file_mode = "w"

    # ── Processing Loop ───────────────────────────────────────────────────────
    with open(out_file, file_mode, encoding="utf-8") as f:
        for i, rec in enumerate(records):
            # Skip records that are already in the output file
            if i < already_processed:
                continue

            assistant_msg = next((m["content"] for m in rec["messages"] if m["role"] == "assistant"), "")
            
            reasoning = ""
            think_match = re.search(r'<think>\s*(.*?)\s*</think>', assistant_msg, re.DOTALL | re.IGNORECASE)
            if think_match:
                reasoning = think_match.group(1)
            
            command = ""
            cmd_match = re.search(r'```(?:bash|sh)?\s*\n(.*?)\n```', assistant_msg, re.DOTALL | re.IGNORECASE)
            if cmd_match:
                command = cmd_match.group(1)

            old_vector = rec.get("attack_vector", "Unknown")
            new_vector = classify_with_slm(reasoning, command, assistant_msg)
            
            rec["attack_vector"] = new_vector.split(" (Raw SLM:")[0]
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush() # Live flush to disk to ensure checkpointing
            
            disp = new_vector if not new_vector.startswith("Unknown") else new_vector
            output_str = f"  [{i+1}/{total}] {old_vector} -> {disp}"
            sys.stdout.write(f"\r{output_str.ljust(100)}")
            sys.stdout.flush()
            
    print(f"\n[DONE] Finished writing to {out_file}")

if __name__ == "__main__":
    BACKEND = sys.argv[1] if len(sys.argv) > 1 else "openai"
    MODE = sys.argv[2].lower().strip() if len(sys.argv) > 2 else "both"

    if MODE not in ("both", "golden", "silver"):
        print(f"[ERROR] Invalid mode '{MODE}'. Must be 'golden', 'silver', or 'both'.")
        sys.exit(1)

    GOLDEN_FILE = f"{BACKEND}_golden_dataset.jsonl"
    SILVER_FILE = f"{BACKEND}_silver_dataset.jsonl"
    OUT_GOLDEN = f"{BACKEND}_golden_dataset_reclassified.jsonl"
    OUT_SILVER = f"{BACKEND}_silver_dataset_reclassified.jsonl"

    print(f"==================================================")
    print(f"  SLM ATTACK VECTOR RE-CLASSIFIER [{BACKEND.upper()}]")
    print(f"  Target Mode: {MODE.upper()}")
    print(f"==================================================")
    
    try:
        requests.get(f"{LOCAL_SLM_BASE_URL}/models", timeout=2)
    except Exception:
        print(f"[FATAL] Cannot connect to local SLM at {LOCAL_SLM_BASE_URL}")
        sys.exit(1)

    if MODE in ("both", "golden"):
        process_file(GOLDEN_FILE, OUT_GOLDEN)
        
    if MODE in ("both", "silver"):
        process_file(SILVER_FILE, OUT_SILVER)
    
    print("\n[SUCCESS] Reclassification complete.")
