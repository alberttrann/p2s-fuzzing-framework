"""Command-line interface for the P2S SDK."""
from __future__ import annotations

import argparse
from pathlib import Path

from .sdk import P2S


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="p2s",
        description="P2S: execution-verified API security testing and dataset generation",
    )
    parser.add_argument(
        "mode",
        choices=[
            "doctor", "patch", "fetch-openapi", "auth", "prepare", "proxy", "record", "compile", "fuzz",
            "generate-data", "prepare-dataset", "coverage", "cleanup",
            "analyze", "reclassify", "m1", "verify", "fd",
        ],
    )
    parser.add_argument("-c", "--config", help="Path to config TOML")
    parser.add_argument("--workdir", default=".", help="Runtime artifact directory")
    parser.add_argument("--dir", default=".", help="Dataset directory for analyze mode")
    parser.add_argument("--backend", default="llamacpp", help="Backend prefix")
    parser.add_argument("--slm-url", default="http://localhost:1234/v1")
    parser.add_argument("--golden-file", default="llamacpp_golden_dataset_reclassified.jsonl")
    parser.add_argument("--verified-out", default="seal_p2s_verified_goldens.jsonl")
    parser.add_argument("--dedup-out", default="", help="Optional output JSONL for strict 5xx FD dedup")
    parser.add_argument("--time-budget", type=int, default=None, help="Override fuzz wall-clock budget in seconds")
    parser.add_argument("--cyclic", action="store_true", help="Cycle traces until the time budget expires")
    parser.add_argument("--no-openapi-patch", action="store_true", help="Do not relax non-path OpenAPI required constraints")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    config_modes = {
        "doctor", "patch", "fetch-openapi", "auth", "prepare", "proxy", "record", "compile", "fuzz",
        "generate-data", "prepare-dataset", "coverage", "cleanup",
    }
    if args.mode in config_modes and not args.config:
        parser.error(f"--config is required for mode '{args.mode}'")

    sdk = P2S.from_toml(args.config, workdir=args.workdir) if args.config else None

    if args.mode == "doctor":
        issues = sdk.doctor()
        if issues:
            for issue in issues:
                print(f"[FAIL] {issue}")
            raise SystemExit(2)
        print("[OK] P2S research configuration passed preflight checks")
    elif args.mode == "patch":
        sdk.patch()
    elif args.mode == "fetch-openapi":
        sdk.fetch_openapi()
    elif args.mode == "auth":
        sdk.acquire_auth()
    elif args.mode == "prepare":
        sdk.prepare()
    elif args.mode == "proxy":
        sdk.run_proxy()
    elif args.mode == "record":
        sdk.record()
    elif args.mode == "compile":
        sdk.compile()
    elif args.mode == "fuzz":
        sdk.fuzz(
            time_budget_seconds=args.time_budget,
            cyclic=True if args.cyclic else None,
            patch_openapi=False if args.no_openapi_patch else None,
        )
    elif args.mode == "generate-data":
        sdk.generate_data()
    elif args.mode == "prepare-dataset":
        sdk.prepare_dataset()
    elif args.mode == "coverage":
        sdk.coverage()
    elif args.mode == "cleanup":
        sdk.cleanup()
    elif args.mode == "analyze":
        from .analytics.analyzer import (
            GOLDEN_SUFFIX, SILVER_SUFFIX, METADATA_SUFFIX,
            RunPair, analyze_run, print_report,
        )
        directory = Path(args.dir)
        pairs = []
        for gf in sorted(directory.glob(f"*{GOLDEN_SUFFIX}")):
            label = gf.name.removesuffix(GOLDEN_SUFFIX)
            sf = directory / f"{label}{SILVER_SUFFIX}"
            mf = directory / f"{label}{METADATA_SUFFIX}"
            if sf.exists():
                pairs.append(RunPair(label, gf, sf, mf))
        if not pairs:
            print("[WARN] No matching dataset pairs found.")
        else:
            print_report([analyze_run(pair) for pair in pairs])
    elif args.mode == "reclassify":
        from .analytics.reclassifier import process_file
        process_file(
            f"{args.backend}_golden_dataset.jsonl",
            f"{args.backend}_golden_dataset_reclassified.jsonl",
            args.slm_url,
        )
        process_file(
            f"{args.backend}_silver_dataset.jsonl",
            f"{args.backend}_silver_dataset_reclassified.jsonl",
            args.slm_url,
        )
    elif args.mode == "m1":
        from .analytics.m1_analyzer import run_m1_analysis
        run_m1_analysis(backend_prefix=args.backend)
    elif args.mode == "verify":
        from .analytics.verifier import verify_golden_file, deduplicate_goldens
        verify_golden_file(args.golden_file, args.verified_out)
        deduplicate_goldens(args.verified_out)
    elif args.mode == "fd":
        from .analytics.faults import deduplicate_5xx_faults
        deduplicate_5xx_faults(args.golden_file, args.dedup_out or None)


if __name__ == "__main__":
    main()
