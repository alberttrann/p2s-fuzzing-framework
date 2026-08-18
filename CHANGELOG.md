# Changelog

## 1.2.0 — Framework-native research reproduction

### Added

- Framework-native research lifecycle: `patch`, `fetch-openapi`, `auth`, `prepare`, `record`, `coverage`, and `cleanup`.
- Idempotent target patches: literal replace, regex replace, exact write, append.
- Declarative OpenAPI download/sanitization and controlled bearer-token acquisition.
- Git-Bash-aware shell dispatch for Windows research lifecycle/reset commands.
- `command` state adapter for heterogeneous RESTgym reset primitives.
- OCLI bearer-token file/environment support and Basic-auth profiles.
- JSON/YAML OpenAPI compilation and form-urlencoded request-body handling.
- Hard wall-clock budgets and cyclic execution for Track B.
- Per-flow/per-target reset policy, configurable prefix replay, and strict Track-B 2xx candidate guard.
- `research.record_trace_source`, allowing a target workload that already emits P2S primitive traces to be frozen without replacing a semantically active target proxy.
- Framework-native research configs for AITasker, SEAL Track A, baseline target preparation, and all 11 RESTgym services.
- New primary `docs/` focused on reproducing the research with the public framework.

### Changed

- Historical reproduction material moved to `original_reporducibility_docs/`.
- Track B now keeps RESTgym's own mitmproxy on historical host port `9090`; the retained `record_*` scripts are workload fixtures only, while compilation/fuzzing/reset orchestration use P2S v1.2.
- Track A model comparison now uses one framework evaluator with model differences expressed in TOML.
- AutoRestTest final-run documentation resolves the archival model discrepancy in favor of **DeepSeek-V4-Flash**, as used by the completed original experiment.
- Package version bumped to `1.2.0`.

### Preserved

- The historical/original one-off scripts and full-fidelity documents remain available for audit and provenance.
- Candidate-vs-verified Track-A distinction, strict 5xx-only Track-B accounting, and the no-synthetic-AUC measurement boundary.

## 1.1.0

- First packaged public SDK release.
- Proxy, compiler, state adapters, fuzzer, dataset builder, analytics, CLI, and high-level SDK.
- Initial research reproducibility documentation and model-serving guidance.

## 1.2.0 — framework-native research reproduction refactor

- Renamed the historical reproduction material to `original_reporducibility_docs/` and made `docs/` the maintained framework-native reproduction path.
- Added canonical `docs/REPRODUCIBILITY.md`, Track-A/Track-B framework reproduction guides, configuration reference, model/training guide, and historical-to-framework mapping.
- Moved research differences into P2S configuration/lifecycle/state abstractions so AITasker, Track A, and Track B use the same proxy/compiler/evaluator package.
- Preserved RESTgym semantic proxy/authentication behavior and per-service Docker/reset patches in declarative research profiles.
- Confirmed the completed original AutoRestTest Track-A run used `DeepSeek-V4-Flash`; older base-Qwen AutoRestTest templates are archival only.
