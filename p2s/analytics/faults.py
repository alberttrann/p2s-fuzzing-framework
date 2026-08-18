"""Status-aligned 5xx fault accounting for Track-B/SBFT-style reporting."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .verifier import extract_error_msg


def _response_evidence(record: dict[str, Any]) -> Any:
    messages = record.get("messages", [])
    if messages and isinstance(messages, list):
        return messages[-1].get("content", "")
    response = record.get("response", {})
    return response.get("body", "") if isinstance(response, dict) else response


def deduplicate_5xx_faults(input_file: str, output_file: str | None = None) -> dict[str, Any]:
    """Filter to HTTP 5xx *before* deduplication and return status-aligned counts.

    This is intentionally separate from generic Golden deduplication because P2S
    Golden files may also contain guarded 2xx security-intent candidates.  SBFT
    Fault Detection is 5xx-only, so mixed-status deduplication would inflate the
    proxy metric.
    """
    path = Path(input_file)
    if not path.exists():
        raise FileNotFoundError(path)

    raw_goldens = 0
    five_xx_records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            raw_goldens += 1
            try:
                status = int(rec.get("actual_status"))
            except (TypeError, ValueError):
                continue
            if 500 <= status <= 599:
                five_xx_records.append(rec)

    unique: dict[tuple[str, int, str], dict[str, Any]] = {}
    for rec in five_xx_records:
        endpoint = str(rec.get("endpoint", "unknown"))
        status = int(rec.get("actual_status", 500))
        signature = extract_error_msg(_response_evidence(rec))
        key = (endpoint, status, signature)
        if key not in unique:
            unique[key] = rec

    if output_file:
        out = Path(output_file)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as f:
            for rec in unique.values():
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    result = {
        "input": str(path),
        "raw_goldens": raw_goldens,
        "raw_5xx_records": len(five_xx_records),
        "unique_5xx_signatures": len(unique),
        "excluded_non_5xx_goldens": raw_goldens - len(five_xx_records),
        "output": output_file or "",
    }
    print("=" * 72)
    print("  P2S STRICT STATUS-ALIGNED 5XX FAULT DEDUPLICATION")
    print(f"  Input Golden records     : {raw_goldens}")
    print(f"  5xx records after filter : {len(five_xx_records)}")
    print(f"  Unique 5xx signatures    : {len(unique)}")
    print(f"  Excluded non-5xx Goldens : {raw_goldens - len(five_xx_records)}")
    if output_file:
        print(f"  Deduplicated output      : {output_file}")
    print("=" * 72)
    return result


__all__ = ["deduplicate_5xx_faults"]
