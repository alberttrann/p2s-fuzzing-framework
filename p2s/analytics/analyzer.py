"""
P2S Analytics: Post-hoc comparative analysis engine.
Recomputes M1, M2, M3, step depth, and vector kill rates across multiple backends.
"""
from __future__ import annotations
import json, re, sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

GOLDEN_SUFFIX = "_golden_dataset.jsonl"
SILVER_SUFFIX = "_silver_dataset.jsonl"
METADATA_SUFFIX = "_run_metadata.json"

LEGACY_VECTOR_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"null.?byte|\\x00|%00", re.I),                       "Null-Byte"),
    (re.compile(r"type.?confusion|integer.*string", re.I),             "Type Confusion"),
    (re.compile(r"integer.?boundar|2147483647|9223372", re.I),         "Integer Boundary"),
    (re.compile(r"string.?extreme|empty.?string|50.?000", re.I),       "String Extremes"),
    (re.compile(r"sql.?inject|sqli|or.1.=.1", re.I),                  "SQLi"),
    (re.compile(r"xss|script.*alert", re.I),                           "XSS"),
    (re.compile(r"encod|url.?encod|double.?encod", re.I),              "Encoding"),
    (re.compile(r"omit|mandatory|missing.?field|required", re.I),      "Mandatory Omission"),
    (re.compile(r"conflict|mutually.?exclusive", re.I),                "Parameter Conflict"),
    (re.compile(r"idor|path.?travers|resource.?id", re.I),             "IDOR"),
    (re.compile(r"mass.?assign|read.?only|owasp.?api3", re.I),        "Mass Assignment"),
    (re.compile(r"bola|bfla|rbac|bypass|escalat|unauthorized", re.I),  "BOLA/BFLA"),
    (re.compile(r"business.?flow|skip.*step|prerequisite", re.I),      "Business Flow"),
    (re.compile(r"replay|idempoten|concurrent", re.I),                 "Replay"),
    (re.compile(r"desync|mismatch.*uuid|context", re.I),               "Context Desync"),
    (re.compile(r"premature|draft|pending.*transit", re.I),            "Premature Progression"),
]

@dataclass
class LoadStats:
    path: str; records: int = 0; blank_lines: int = 0
    malformed_lines: int = 0; recovered_records: int = 0

@dataclass
class M2Stats:
    total: int = 0; exact_match: int = 0; class_match: int = 0
    no_prediction: int = 0; no_actual: int = 0
    invalid_prediction: int = 0; invalid_actual: int = 0
    mismatches: list[dict[str, Any]] = field(default_factory=list)

@dataclass
class RunPair:
    label: str; golden_path: Path; silver_path: Path; metadata_path: Path

def percentage(numerator: float, denominator: float) -> float:
    return 100.0 * float(numerator) / float(denominator) if denominator else 0.0

def load_jsonl(path: Path) -> tuple[list[dict[str, Any]], LoadStats]:
    stats = LoadStats(path=str(path)); records: list[dict[str, Any]] = []
    if not path.exists(): return records, stats
    decoder = json.JSONDecoder()
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line: stats.blank_lines += 1; continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict): records.append(obj); continue
            except json.JSONDecodeError: pass
            pos = 0; recovered = []
            while pos < len(line):
                while pos < len(line) and line[pos].isspace(): pos += 1
                if pos >= len(line): break
                try:
                    obj, end = decoder.raw_decode(line, pos)
                    if isinstance(obj, dict): recovered.append(obj)
                    pos = end
                except json.JSONDecodeError: break
            if recovered:
                records.extend(recovered); stats.recovered_records += len(recovered)
            else:
                stats.malformed_lines += 1
    stats.records = len(records)
    return records, stats

def compute_m2(records: Iterable[dict[str, Any]]) -> M2Stats:
    stats = M2Stats()
    for record in records:
        predicted = record.get("predicted_status")
        actual = record.get("actual_status")
        if predicted is None: stats.no_prediction += 1; continue
        if actual is None: stats.no_actual += 1; continue
        stats.total += 1
        if int(predicted) == int(actual):
            stats.exact_match += 1; stats.class_match += 1
        else:
            if int(predicted) // 100 == int(actual) // 100: stats.class_match += 1
            stats.mismatches.append({
                "predicted": predicted, "actual": actual,
                "endpoint": record.get("endpoint", "unknown")
            })
    return stats

def analyze_run(pair: RunPair) -> dict[str, Any]:
    goldens, _ = load_jsonl(pair.golden_path)
    silvers, _ = load_jsonl(pair.silver_path)
    metadata = None
    if pair.metadata_path.exists():
        with open(pair.metadata_path, encoding="utf-8") as f: metadata = json.load(f)

    total_records = len(goldens) + len(silvers)
    m2_golden = compute_m2(goldens)
    m2_silver = compute_m2(silvers)
    golden_vectors = Counter(r.get("attack_vector", "Unknown") for r in goldens)
    silver_vectors = Counter(r.get("attack_vector", "Unknown") for r in silvers)

    vector_kill_rates = {}
    for v in sorted(set(golden_vectors) | set(silver_vectors)):
        g = golden_vectors.get(v, 0); s = silver_vectors.get(v, 0)
        vector_kill_rates[v] = {
            "golden": g, "silver": s, "total": g + s,
            "kill_rate_pct": percentage(g, g + s)
        }

    golden_steps = Counter(
        len(re.findall(r"^Step\s+\d+\s*:", m.get("content", ""), re.M)) + 1
        for r in goldens for m in r.get("messages", []) if m.get("role") == "user"
    )

    return {
        "label": pair.label,
        "golden_count": len(goldens), "silver_count": len(silvers),
        "total_records": total_records,
        "m2_golden": asdict(m2_golden), "m2_silver": asdict(m2_silver),
        "m3": {
            "kill_rate_pct": percentage(len(goldens), total_records),
            "records_per_golden": total_records / len(goldens) if goldens else None
        },
        "golden_steps": dict(golden_steps),
        "vector_kill_rates": vector_kill_rates,
        "metadata": metadata
    }

def print_report(runs: list[dict[str, Any]]):
    print("═" * 80)
    print("  P2S EVALUATION — COMPARATIVE ANALYSIS REPORT")
    print("═" * 80)
    for run in runs:
        print(f"\n▶ [{run['label'].upper()}]")
        print(f"  Total Records        : {run['total_records']}")
        print(f"  Golden / Silver      : {run['golden_count']} / {run['silver_count']}")
        print(f"  M3 Kill Rate         : {run['m3']['kill_rate_pct']:.2f}%")
        rpg = run['m3']['records_per_golden']
        print(f"  Records per Golden   : {rpg:.1f}" if rpg else "  Records per Golden   : N/A")
        print(f"  M2 Golden (Exact)    : {run['m2_golden']['exact_match']}/{run['m2_golden']['total']}")
        print(f"  M2 Silver (Exact)    : {run['m2_silver']['exact_match']}/{run['m2_silver']['total']} "
              f"(Class: {run['m2_silver']['class_match']})")
        gs = run['golden_steps']
        print(f"  Max Step Depth       : {max(gs.keys()) if gs else 'None'}")
    print("\n" + "═" * 80)
