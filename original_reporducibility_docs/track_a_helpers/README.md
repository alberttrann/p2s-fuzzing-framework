# Track-A historical-parity helpers

These files are extracted from the user-supplied Track-A experiment notes so the public reproducibility guide does not hide implementation-critical behavior behind prose.

- `proxy_seal_historical.py` — thread-safe `X-Flow-ID` proxy with sensitive-header masking.
- `seal_flows_historical.sh` — 21-flow SEAL/HackathonBench trace driver. Literal test passwords are parameterized through environment variables.
- `trace_compiler_seal_historical.py` — SEAL compiler with `/api` stripping, malformed `//` skip, richer catalog, and `$ref` query-type handling.
- `eval_student_p2s_engine_historical_sanitized.py` — archived audit-fixed evaluator logic. Hard-coded provider API-key defaults are removed; supply keys through environment variables.
- `validate_seal_goldens.py`, `deduplicate_goldens.py`, `reclassify_vectors.py` — archived post-processing helpers.
- `sanitize_baseline_openapi.py` — shared conventional-baseline contract sanitization.
- `verify_long_lived_jwt.py` — checks the currently running local backend token lifetime.
- `autoresttest_posthoc_audit.py` — defensible persisted-artifact audit.
- `cats_schemathesis_posthoc_audit.py` — source-derived CATS/Schemathesis parser with interpretation warnings.

**Security hygiene:** any literal third-party API keys found in historical notes are intentionally not reproduced. This is the only deliberate byte-level divergence in the evaluator helper.
