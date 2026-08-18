# P2S Framework v1.2.0 Release Notes

v1.2.0 is a reproducibility-focused refactor. The core research path no longer asks users to switch among historical P2S proxy/compiler/evaluator files for different experiments.

The package now absorbs those implementation differences through lifecycle configuration, OpenAPI/auth preparation, generalized reset adapters, improved compilation, hard budget/cyclic execution controls, and Git-Bash-aware command dispatch on Windows.

## Documentation split

- `docs/` — canonical framework-native reproduction.
- `original_reporducibility_docs/` — frozen historical/original procedures and helper scripts.

## Track A

The P2S specialist, base Qwen control, and DeepSeek control now use the same framework evaluator. A separate baseline-preparation config patches the long-lived SEAL test JWT, sanitizes the shared OpenAPI contract, and acquires the controlled Coordinator credential for AutoRestTest/CATS/Schemathesis.

The completed original **AutoRestTest** experiment used **DeepSeek-V4-Flash**; v1.2 documents that as authoritative and marks older local-Qwen baseline setup text as archival.

## Track B

Every RESTgym service uses a v1.2 TOML describing its mandatory Phase-1 adaptations and reset mechanism. RESTgym's own mitmproxy remains on host port 9090 because its authentication/request-rewrite behavior is part of the target environment. Workload fixtures produce P2S primitive traces, while `p2s compile` and `p2s fuzz` are shared across all 11 services.

## Compatibility

The Python API remains centered on `P2S.from_toml(...)`. Existing simpler v1.1 configs continue to parse because the new fields have defaults; research configs can opt into the v1.2 lifecycle features incrementally.
