# Changelog

## 1.1.0 — SDK packaging

- Added the high-level `P2S` / `P2SClient` Python SDK facade.
- Added stable top-level imports and `__version__`.
- Added `p2s.cli` and `python -m p2s` entry points.
- Preserved `p2s_runner.py` as a backward-compatible shim.
- Added SDK-managed proxy, compiler, fuzzer, generator, and dataset workflows.
- Added `P2SError` / `P2SConfigurationError` and OpenAPI patch utility.
- Added PEP 561 `py.typed` marker.
- Added wheel-ready package metadata and optional Transformers dependencies.
- Added SDK smoke tests and SDK usage documentation.
