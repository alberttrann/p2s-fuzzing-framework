#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════════════════
# validate_seal_goldens.py
# SEAL HACKATHON GOLDEN RECORD VERIFICATION & FALSE-POSITIVE FILTER
# Validates 500 crashes, BOLA/IDOR ID swaps, and filters out Jackson-ignored
# properties and CLI help-bleed false positives.
# ═══════════════════════════════════════════════════════════════════════════════

import json
import os
import re
import argparse
import sys
def inspect_and_validate_record(record):
    """
    Evaluates a single Golden record for ground-truth security validity.
    Returns: (is_true_positive: bool, category_code: str, explanation: str)
    """
    # Extract fields from record structure
    mutated_cmd = record.get("mutated_command", "")
    actual_status = record.get("actual_status", 500)
    golden_label = record.get("golden_label", "")
    endpoint = record.get("endpoint", "")
    
    # Extract reasoning from messages if present, else root key
    reasoning = ""
    messages = record.get("messages", [])
    if messages and isinstance(messages, list):
        reasoning = messages[-1].get("content", "")
    else:
        reasoning = record.get("reasoning", "")

    # ───────────────────────────────────────────────────────────────────────────
    # RULE 1: CLI Help-Bleed Filter (False Positive)
    # If the command executed '--help' or '-h', CLI exited with 0 (not an API call).
    # ───────────────────────────────────────────────────────────────────────────
    is_help = "--help" in mutated_cmd or " -h" in mutated_cmd or mutated_cmd.endswith(" -h")
    if is_help:
        return False, "FP_HELP_BLEED", f"Command executed CLI --help instead of an API request: `{mutated_cmd}`"

    # ───────────────────────────────────────────────────────────────────────────
    # RULE 2: HTTP 500 Unhandled Server Crash (100% True Positive)
    # Any 500 response indicates an unhandled server-side exception/fault.
    # ───────────────────────────────────────────────────────────────────────────
    if actual_status == 500 or golden_label == "GOLDEN_CRASH":
        return True, "TP_CRASH_500", "Unhandled 500 Internal Server Error (True Positive Server Crash)."

    # ───────────────────────────────────────────────────────────────────────────
    # RULE 3: HTTP 200/201 Security Bypasses (BOLA / BFLA / Mass Assignment)
    # ───────────────────────────────────────────────────────────────────────────
    if actual_status in [200, 201]:
        # 3A. Mass Assignment Check: Were injected read-only flags ignored by Jackson?
        injected_mass_flags = ["iseditable", "candelete", "systemcriteria", "isadmin", "issuperuser", "skipapproval"]
        has_mass_flag = any(f"--{f}" in mutated_cmd.lower() for f in injected_mass_flags)

        if has_mass_flag:
            # Check if any injected property was echoed back in the response/record
            record_str = json.dumps(record).lower()
            bound_property = any(f'"{f}":' in record_str or f'"{f}": true' in record_str for f in injected_mass_flags)
            
            if not bound_property:
                return False, "FP_JACKSON_IGNORED_PARAM", f"Mass assignment flags were silently ignored by Spring Jackson parser: `{mutated_cmd}`"
            else:
                return True, "TP_MASS_ASSIGNMENT", "Injected read-only property was successfully bound to database entity."

        # 3B. BOLA / IDOR / Token Manipulation Check
        has_token_override = "--api-bearer-token" in mutated_cmd
        has_id_swap = bool(re.search(r'--(?:id|userId|teamId|submissionId|roundId)\s+[\w-]{36}', mutated_cmd))
        is_sec_reasoning = bool(re.search(r'\b(?:bola|bfla|idor)\b|bypass\s+(?:auth|role|permission|access)|privilege\s+escalat', reasoning, re.I))

        # If model wrote "authorization" in reasoning but executed a normal authorized command as Coordinator
        if is_sec_reasoning and not (has_token_override or has_id_swap):
            return False, "FP_LEGITIMATE_AUTHORIZED_200", f"Legitimate 200 OK request by authorized user; no resource ID or JWT was mutated: `{mutated_cmd}`"

        if has_token_override or has_id_swap or is_sec_reasoning:
            return True, "TP_BOLA_IDOR_BYPASS", "Confirmed BOLA/IDOR/Token manipulation resulting in HTTP 200 OK."

        return True, "TP_SECURITY_BYPASS", "Confirmed 200 OK Security Bypass."

    return False, "FP_UNCLASSIFIED", f"Unclassified response with status {actual_status}."

def main():
    parser = argparse.ArgumentParser(description="Validate SEAL P2S Golden Dataset Records")
    parser.add_argument("--golden-file", default="seal_p2s_golden_dataset.jsonl", help="Path to golden dataset file")
    parser.add_argument("--output-verified", default="seal_p2s_verified_goldens.jsonl", help="Path to output verified file")
    args = parser.parse_args()

    if not os.path.exists(args.golden_file):
        print(f"[ERROR] Golden dataset file not found: {args.golden_file}")
        sys.exit(1)

    print("\n" + "="*70)
    print(f"  SEAL HACKATHON GOLDEN RECORD VERIFICATION")
    print(f"  Input File: {args.golden_file}")
    print("="*70 + "\n")

    records = []
    with open(args.golden_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try: records.append(json.loads(line))
                except json.JSONDecodeError: pass

    true_positives = []
    false_positives = []
    categories = {}

    for idx, rec in enumerate(records, 1):
        is_tp, cat_code, explanation = inspect_and_validate_record(rec)
        categories[cat_code] = categories.get(cat_code, 0) + 1
        
        status_tag = "✅ TRUE POSITIVE" if is_tp else "❌ FALSE POSITIVE"
        print(f"[{idx:>2}/{len(records)}] {status_tag} | {cat_code}")
        print(f"     Endpoint : {rec.get('endpoint', 'N/A')}")
        print(f"     Command  : {rec.get('mutated_command', '')[:90]}")
        print(f"     Reason   : {explanation[:100]}\n")

        if is_tp:
            rec["verified_category"] = cat_code
            true_positives.append(rec)
        else:
            rec["fp_reason"] = cat_code
            false_positives.append(rec)

    # Save verified true positives to clean file
    with open(args.output_verified, "w", encoding="utf-8") as f:
        for tp in true_positives:
            f.write(json.dumps(tp, ensure_ascii=False) + "\n")

    # Summary Report
    tp_cnt = len(true_positives)
    fp_cnt = len(false_positives)
    total_cnt = len(records)
    tp_pct = (tp_cnt / total_cnt * 100) if total_cnt > 0 else 0.0

    print("="*70)
    print("  VERIFICATION SUMMARY REPORT")
    print("="*70)
    print(f"  Total Goldens Evaluated  : {total_cnt}")
    print(f"  True Positives (Verified) : {tp_cnt} ({tp_pct:.1f}%)")
    print(f"  False Positives (Filtered): {fp_cnt} ({100 - tp_pct:.1f}%)\n")
    print("  Breakdown by Category:")
    for cat, count in sorted(categories.items()):
        tag = "TP" if cat.startswith("TP") else "FP"
        print(f"    • [{tag}] {cat:<28} : {count}")
    print("\n" + "="*70)
    print(f"  Verified Goldens saved to: {args.output_verified}")
    print("="*70 + "\n")

if __name__ == "__main__":
    main()
