# P2S Framework v1.2 Package Notes

This source release contains the installable P2S package plus the framework-native research configurations and documentation.

## Included

```text
p2s/                         Python SDK/CLI implementation
configs/research/            framework-native experiment configs
docs/                        canonical v1.2 reproduction docs
original_reporducibility_docs/ historical/original reproduction archive
tests/                       SDK/research-config/compiler tests
README.md
CHANGELOG.md
RELEASE_NOTES_v1.2.0.md
```

## v1.2 reproducibility refactor

The previous release preserved exact historical operations by documenting one-off proxy/compiler/evaluator files. v1.2 retains those files in the historical archive but moves the primary experiment workflow into the reusable package:

- target/environment patches are TOML-driven;
- OpenAPI acquisition/sanitization is framework-native;
- controlled test authentication can be acquired by the framework;
- OCLI credentials are configuration-driven;
- heterogeneous reset mechanisms use standard adapters;
- one compiler supports JSON/YAML and form-urlencoded contracts;
- one fuzzer supports Track-A state replay and Track-B cyclic time budgets;
- Track-B workload-produced primitive traces can be frozen through `record_trace_source` while preserving RESTgym's own mitmproxy.

## External components intentionally not absorbed into P2S

Target repositories still provide their valid workflow fixtures, and conventional baseline tools remain independent:

```text
AITasker mainflow suite
SEAL business-flow suite
RESTgym record_* workload fixtures
AutoRestTest
CATS
Schemathesis
```

These define traffic or external baseline behavior; they are not alternate P2S implementations.

## AutoRestTest source-of-truth correction

The completed original Track-A AutoRestTest experiment used **DeepSeek-V4-Flash**. Older archival local-base-Qwen setup text remains available only as provenance.
