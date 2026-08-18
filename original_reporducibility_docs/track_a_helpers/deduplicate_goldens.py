import json
import os
import re

def extract_error_msg(res_body):
    """Extracts clean exception signature from HTTP response body."""
    if isinstance(res_body, dict):
        msg = res_body.get("message") or res_body.get("error") or ""
        return str(msg).strip()
    elif isinstance(res_body, str):
        # Look for SQL/Hibernate/Java exception patterns
        m = re.search(r'([a-zA-Z0-9_.]*(?:Exception|Error)[^\n\r"]*)', res_body)
        if m: return m.group(1).strip()
        return res_body[:90].strip()
    return "Unknown 5xx Error"

def deduplicate_goldens(file_path):
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found.")
        return

    unique_faults = {}
    raw_count = 0

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            raw_count += 1
            rec = json.loads(line)

            endpoint = rec.get("endpoint", "unknown")
            actual_status = rec.get("actual_status", 500)
            
            # Extract response body from message thread
            res_body = None
            messages = rec.get("messages", [])
            if messages and isinstance(messages, list):
                res_body = messages[-1].get("content", "")
            else:
                res_body = rec.get("response", {}).get("body", "")

            err_msg = extract_error_msg(res_body)

            # Unique Fault Signature = (Endpoint + Status + Exception Signature)
            fault_key = (endpoint, actual_status, err_msg)

            if fault_key not in unique_faults:
                unique_faults[fault_key] = {
                    "count": 1,
                    "sample_cmd": rec.get("mutated_command", ""),
                    "endpoint": endpoint,
                    "status": actual_status,
                    "error_msg": err_msg
                }
            else:
                unique_faults[fault_key]["count"] += 1

    print("\n" + "=" * 75)
    print("  P2S UNIQUE 5XX FAULT DEDUPLICATION REPORT")
    print(f"  Input File           : {file_path}")
    print(f"  Raw Golden Exploits  : {raw_count}")
    print(f"  UNIQUE 5XX FAULTS    : {len(unique_faults)}")
    print("=" * 75 + "\n")

    for idx, (key, info) in enumerate(unique_faults.items(), 1):
        print(f"  [{idx:>2}] HTTP {info['status']} | Endpoint: {info['endpoint']}")
        print(f"       Exception Signature : {info['error_msg'][:80]}")
        print(f"       Sample Command      : {info['sample_cmd'][:80]}")
        print(f"       Triggered           : {info['count']} times\n")

    print("=" * 75)
    return len(unique_faults), raw_count

if __name__ == "__main__":
    import sys
    golden_file = sys.argv[1] if len(sys.argv) > 1 else "blog_p2s_golden_dataset.jsonl"
    deduplicate_goldens(golden_file)
