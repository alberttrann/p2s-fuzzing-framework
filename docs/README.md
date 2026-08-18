# P2S Framework v1.2 — Documentation

This directory is the **canonical framework-native documentation**. It explains how to use the public `p2s` package as the shared implementation for custom targets and for reproducing the research.

Historical one-off scripts and exact development-era procedures are intentionally separated under `original_reporducibility_docs/`.

## New user path

1. **[Getting Started](GETTING_STARTED.md)** — install the wheel/source package, understand external prerequisites, and run your first target.
2. **[Root README](../README.md)** — research motivation, architecture, training, results, limitations, public models, and project map.
3. **[SDK Guide](../SDK_GUIDE.md)** — Python methods, CLI equivalence, adapters, artifacts, and troubleshooting.
4. **[Configuration Reference](CONFIGURATION_REFERENCE.md)** — full TOML schema.

## Full research reproduction

1. [Master reproduction](REPRODUCIBILITY.md)
2. [Track A with P2S Framework](TRACK_A_WITH_P2S_FRAMEWORK.md)
3. [Track B / RESTgym with P2S Framework](TRACK_B_WITH_P2S_FRAMEWORK.md)
4. [Model, training, and serving](MODEL_AND_TRAINING.md)
5. [Historical-to-framework mapping](HISTORICAL_TO_FRAMEWORK_MAPPING.md)
6. [Framework refactor notes](FRAMEWORK_REFACTOR_NOTES.md)

## Development / packaging

- [Build and release](BUILD_AND_RELEASE.md) — explains `build/`, `dist/`, wheel creation, clean installs, and GitHub release practice.

## Documentation split

```text
docs/
    current public framework path

original_reporducibility_docs/
    historical experiment implementation archive
```

The maintained docs do **not** require the old per-operation `trace_compiler.py`, `eval_student_p2s_engine.py`, or target-specific P2S proxy forks. Target repositories still retain their workload fixtures because those define *what business state to exercise*, not a different P2S algorithm.

**AutoRestTest final-run source of truth:** DeepSeek-V4-Flash.
