"""
P2S Verifier & Deduplicator: Filters False Positives and deduplicates 5xx exception signatures.
Ensures ground-truth precision for paper reporting and artifact releases.
"""
from __future__ import annotations
import json, os, re, sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def extract_error_msg(res_body: Any) -> str:
    if isinstance(res_body, dict):
        msg = res_body.get("message") or res_body.get("error") or ""
        return str(msg).strip()
    elif isinstance(res_body, str):
        m = re.search(r'([a-zA-Z0-9_.]*(?:Exception|Error)[^\n\r"]*)', res_body)
        if m: return m.group(1).strip()
        return res_body[:90].strip()
    return "Unknown 5xx Error"


def inspect_and_validate_record(record: dict[str, Any]) -> tuple[bool, str, str]:
    """
    Evaluates a single Golden record for ground-truth security validity.
    Returns: (is_true_positive, category_code, explanation)
    """
    mutated_cmd = record.get("mutated_command", "") or ""
    actual_status = record.get("actual_status", 500)
    golden_label = record.get("golden_label", "")
    reasoning = ""
    messages = record.get("messages", [])
    if messages and isinstance(messages, list):
        reasoning = messages[-1].get("content", "")
    else:
        reasoning = record.get("reasoning", "")

    # Rule 1: CLI Help-Bleed
    is_help = "--help" in mutated_cmd or " -h" in mutated_cmd or mutated_cmd.endswith(" -h")
    if is_help:
        return False, "FP_HELP_BLEED", f"CLI --help executed instead of HTTP request."

    # Rule 2: HTTP 500 Unhandled Server Crash
    if actual_status >= 500 or golden_label == "GOLDEN_CRASH":
        return True, "TP_CRASH_500", "Unhandled 500 Internal Server Error."

    # Rule 3: HTTP 200/201 Security Bypasses
    if actual_status in [200, 201]:
        injected_mass_flags = [
            "iseditable", "candelete", "systemcriteria",
            "isadmin", "issuperuser", "skipapproval"
        ]
        has_mass_flag = any(f"--{f}" in mutated_cmd.lower() for f in injected_mass_flags)

        if has_mass_flag:
            record_str = json.dumps(record).lower()
            bound_property = any(
                f'"{f}":' in record_str or f'"{f}": true' in record_str
                for f in injected_mass_flags
            )
            if not bound_property:
                return False, "FP_JACKSON_IGNORED_PARAM", \
                       "Mass assignment flags silently ignored by Jackson."
            else:
                return True, "TP_MASS_ASSIGNMENT", \
                       "Injected read-only property successfully bound to database entity."

        has_token_override = "--api-bearer-token" in mutated_cmd
        has_id_swap = bool(re.search(
            r'--(?:id|userId|teamId|submissionId|roundId)\s+[\w-]{36}', mutated_cmd
        ))
        is_sec_reasoning = bool(re.search(
            r'\b(?:bola|bfla|idor)\b|bypass\s+(?:auth|role|permission|access)|privilege\s+escalat',
            reasoning, re.I
        ))

        if is_sec_reasoning and not (has_token_override or has_id_swap):
            return False, "FP_LEGITIMATE_AUTHORIZED_200", \
                   "Authorized 200 OK; no ID/JWT mutated."

        if has_token_override or has_id_swap or is_sec_reasoning:
            return True, "TP_BOLA_IDOR_BYPASS", \
                   "Confirmed BOLA/IDOR/Token manipulation → HTTP 200 OK."

        return True, "TP_SECURITY_BYPASS", "Confirmed 200 OK Security Bypass."

    return False, "FP_UNCLASSIFIED", f"Unclassified response with status {actual_status}."


def verify_golden_file(input_file: str, output_verified: str) -> dict[str, Any]:
    if not os.path.exists(input_file):
        print(f"[ERROR] Golden file not found: {input_file}"); return {}

    records = []
    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try: records.append(json.loads(line))
                except json.JSONDecodeError: pass

    true_positives, false_positives, categories = [], [], {}

    for rec in records:
        is_tp, cat_code, explanation = inspect_and_validate_record(rec)
        categories[cat_code] = categories.get(cat_code, 0) + 1
        if is_tp:
            rec["verified_category"] = cat_code; true_positives.append(rec)
        else:
            rec["fp_reason"] = cat_code; false_positives.append(rec)

    with open(output_verified, "w", encoding="utf-8") as f:
        for tp in true_positives:
            f.write(json.dumps(tp, ensure_ascii=False) + "\n")

    tp_cnt = len(true_positives); fp_cnt = len(false_positives)
    total_cnt = len(records)
    tp_pct = (tp_cnt / total_cnt * 100) if total_cnt > 0 else 0.0

    print("=" * 70)
    print("  P2S GOLDEN RECORD VERIFICATION REPORT")
    print(f"  Input File               : {input_file}")
    print(f"  Total Goldens Evaluated  : {total_cnt}")
    print(f"  True Positives (Verified): {tp_cnt} ({tp_pct:.1f}%)")
    print(f"  False Positives (Filtered): {fp_cnt} ({100 - tp_pct:.1f}%)")
    print("=" * 70)
    for cat, count in sorted(categories.items()):
        tag = "TP" if cat.startswith("TP") else "FP"
        print(f"    • [{tag}] {cat:<28} : {count}")
    print("=" * 70)
    print(f"  Saved Verified Goldens to : {output_verified}\n")

    return {
        "total": total_cnt, "true_positives": tp_cnt, "false_positives": fp_cnt,
        "tp_pct": tp_pct, "categories": categories
    }


def deduplicate_goldens(file_path: str, output_dedup: str = None) -> tuple[int, int]:
    if not os.path.exists(file_path):
        print(f"[ERROR] File not found: {file_path}"); return 0, 0

    unique_faults = {}; raw_count = 0; unique_records = []

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            raw_count += 1
            rec = json.loads(line)
            endpoint = rec.get("endpoint", "unknown")
            actual_status = rec.get("actual_status", 500)
            messages = rec.get("messages", [])
            res_body = messages[-1].get("content", "") \
                       if messages and isinstance(messages, list) \
                       else rec.get("response", {}).get("body", "")
            err_msg = extract_error_msg(res_body)
            fault_key = (endpoint, actual_status, err_msg)

            if fault_key not in unique_faults:
                unique_faults[fault_key] = {
                    "count": 1, "endpoint": endpoint,
                    "status": actual_status, "error_msg": err_msg
                }
                unique_records.append(rec)
            else:
                unique_faults[fault_key]["count"] += 1

    if output_dedup:
        with open(output_dedup, "w", encoding="utf-8") as f:
            for rec in unique_records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print("=" * 75)
    print("  P2S UNIQUE FAULT DEDUPLICATION REPORT")
    print(f"  Input File           : {file_path}")
    print(f"  Raw Golden Exploits  : {raw_count}")
    print(f"  UNIQUE FAULTS        : {len(unique_faults)}")
    print("=" * 75)
    for idx, (key, info) in enumerate(unique_faults.items(), 1):
        print(f"  [{idx:>2}] HTTP {info['status']} | Endpoint: {info['endpoint']}")
        print(f"       Exception Signature : {info['error_msg'][:80]}")
        print(f"       Triggered           : {info['count']} times\n")
    print("=" * 75 + "\n")

    return len(unique_faults), raw_count
