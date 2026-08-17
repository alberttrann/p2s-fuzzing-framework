"""
P2S Offline Tier-2 SLM Judge: Reclassifies attack vectors in saved JSONL files.
"""
import json, os, sys, re, requests, time

ALLOWED_CLASSES = [
    "Null-Byte", "Type Confusion", "Integer Boundary", "String Extremes",
    "SQLi", "XSS", "Encoding", "Mandatory Omission", "Parameter Conflict",
    "IDOR", "Mass Assignment", "BOLA/BFLA", "Business Flow", "Replay",
    "Context Desync", "Premature Progression", "Unknown"
]

SYSTEM_PROMPT = """You are an expert cybersecurity classifier.
Classify the following API fuzzing test case into EXACTLY ONE of the 16 categories based
on the reasoning and the command.

1. Null-Byte          2. Type Confusion        3. Integer Boundary      4. String Extremes
5. SQLi              6. XSS                   7. Encoding              8. Mandatory Omission
9. Parameter Conflict 10. IDOR                 11. Mass Assignment      12. BOLA/BFLA
13. Business Flow    14. Replay               15. Context Desync       16. Premature Progression

OUTPUT FORMAT:
Output ONLY the exact name of the category from the list above. No numbers, no explanation."""

def classify_with_slm(reasoning: str, command: str, raw_msg: str,
                      slm_url: str, attempt: int = 1) -> str:
    prompt = (
        f"Reasoning:\n{reasoning}\n\nCommand:\n{command}\n\nCategory Name:"
        if reasoning or command else
        f"Categorize this attack:\n{raw_msg}\n\nCategory Name:"
    )
    payload = {
        "model": "local-model",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.0, "max_tokens": 24000
    }
    try:
        resp = requests.post(f"{slm_url.rstrip('/')}/chat/completions",
                             json=payload, timeout=800)
        resp.raise_for_status()
        msg = resp.json()["choices"][0]["message"]
        raw_output = msg.get("content", "").strip()
        if not raw_output and msg.get("reasoning_content"):
            lines = [l.strip() for l in msg["reasoning_content"].split('\n') if l.strip()]
            if lines: raw_output = lines[-1]
        out_lower = raw_output.lower()
        for cls in ALLOWED_CLASSES:
            if cls.lower() in out_lower: return cls
        # Fuzzy fallback matching
        checks = [
            ("null" in out_lower and "byte" in out_lower, "Null-Byte"),
            ("type" in out_lower and "confusion" in out_lower, "Type Confusion"),
            ("integer" in out_lower or "boundar" in out_lower, "Integer Boundary"),
            ("extreme" in out_lower or "empty string" in out_lower, "String Extremes"),
            ("sql" in out_lower, "SQLi"), ("xss" in out_lower, "XSS"),
            ("encod" in out_lower, "Encoding"),
            ("omit" in out_lower or "mandatory" in out_lower, "Mandatory Omission"),
            ("conflict" in out_lower, "Parameter Conflict"), ("idor" in out_lower, "IDOR"),
            ("mass" in out_lower and "assign" in out_lower, "Mass Assignment"),
            ("bola" in out_lower or "bfla" in out_lower, "BOLA/BFLA"),
            ("business flow" in out_lower, "Business Flow"),
            ("replay" in out_lower, "Replay"), ("desync" in out_lower, "Context Desync"),
            ("premature" in out_lower, "Premature Progression"),
        ]
        for cond, label in checks:
            if cond: return label
        return "Unknown"
    except Exception:
        if attempt < 3:
            time.sleep(1)
            return classify_with_slm(reasoning, command, raw_msg, slm_url, attempt + 1)
        return "Unknown"

def process_file(in_file: str, out_file: str, slm_url: str):
    if not os.path.exists(in_file):
        print(f"[SKIP] File not found: {in_file}"); return
    print(f"[*] Reclassifying {in_file} -> {out_file}...")
    records = []
    with open(in_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip(): records.append(json.loads(line))

    total = len(records)
    valid_lines = []
    if os.path.exists(out_file):
        with open(out_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try: json.loads(line); valid_lines.append(line)
                    except json.JSONDecodeError: break

    already_processed = len(valid_lines)
    if already_processed >= total and total > 0:
        print(f"[SKIP] Already fully processed ({already_processed}/{total})."); return
    if already_processed > 0:
        print(f"[RESUME] Resuming from record {already_processed + 1}/{total}...")
        with open(out_file, "w", encoding="utf-8") as f: f.writelines(valid_lines)
        file_mode = "a"
    else:
        file_mode = "w"

    with open(out_file, file_mode, encoding="utf-8") as f:
        for i, rec in enumerate(records):
            if i < already_processed: continue
            assistant_msg = next(
                (m["content"] for m in rec.get("messages", []) if m["role"] == "assistant"), ""
            )
            reasoning = ""
            think_match = re.search(
                r'<think>\s*(.*?)\s*</think>', assistant_msg, re.DOTALL | re.IGNORECASE
            )
            if think_match: reasoning = think_match.group(1)
            command = ""
            cmd_match = re.search(
                r'```(?:bash|sh)?\s*\n(.*?)\n```', assistant_msg, re.DOTALL | re.IGNORECASE
            )
            if cmd_match: command = cmd_match.group(1)
            rec["attack_vector"] = classify_with_slm(
                reasoning, command, assistant_msg, slm_url
            )
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            sys.stdout.write(f"\r  [{i+1}/{total}] {rec['attack_vector']}")
            sys.stdout.flush()
    print(f"\n[DONE] Finished writing {out_file}")
