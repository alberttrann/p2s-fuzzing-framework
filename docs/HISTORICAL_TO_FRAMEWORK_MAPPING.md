# Historical Research Files → P2S Framework v1.2 Mapping

This document explains exactly what changed when the original per-operation implementation was normalized into P2S v1.2.

The historical files are still preserved in `original_reporducibility_docs/`, but a framework-native reproduction should use the right-hand side of this table.

| Historical responsibility | v1.2 replacement |
|---|---|
| AITasker/SEAL proxy variants | `p2s proxy` + `[proxy]` flow strategy/masking config |
| SEAL-specific `trace_compiler.py` | `p2s compile` + `target.context_path_prefix` |
| RESTgym `trace_compiler.py` | same `p2s compile`; YAML/form-urlencoded support is built in |
| `eval_student_p2s_engine.py` model switching | one `p2s fuzz` implementation + `[llm]` config |
| SEAL cached-OpenAPI required relaxation | `research.patch_openapi_required = true` |
| OCLI profile bootstrap | `[ocli]` + `OcliExecutorAdapter` |
| SEAL Coordinator token helper | `[auth]` + `p2s auth` |
| AutoRestTest/CATS/Schemathesis spec sanitizer | `[openapi_setup]` + `p2s fetch-openapi` |
| PostgreSQL DB recreate/template helpers | `PostgresTemplateAdapter` |
| RESTgym SQL/Mongo/Kafka/contract resets | `CommandStateAdapter` + `[command_state]` |
| Docker-only state reset | `DockerRestartAdapter` or configured command reset |
| Track-B outer one-hour loop | `research.time_budget_seconds=3600`, `cyclic=true` |
| Track-B reset before target | `research.reset_before_each_target=true` |
| Track-A source/SEAL flow baseline reset | `research.reset_before_each_flow=true` |
| Track-B guarded 2xx candidate check | `research.require_attack_flag_for_2xx=true` |
| mixed-status "unique 5xx" helper | `p2s fd`, which filters 5xx before dedup |
| target build/auth/Dockerfile edits | `[[patches]]` + `[research].prepare_commands` |
| workload capture freeze | `p2s record`; source is proxy output or `record_trace_source` |

## What is intentionally still target-specific

A reusable framework cannot infer the valid business workflow of an arbitrary application from nothing. Therefore these remain fixtures in the target research artifacts:

- AITasker mainflow scripts;
- SEAL/HackathonBench business-flow script;
- RESTgym per-service workload recorders;
- service SQL seeds/migrations;
- the actual target applications/containers.

They supply valid state and workload. They do **not** supply a private P2S compiler or evaluator.

## Track B topology change from the first v1.2 draft

An early normalization idea placed P2S's capture proxy on host `9090` and remapped RESTgym's proxy to `9091`. That is no longer the canonical configuration because RESTgym's own proxy has semantic responsibilities (authentication/session handling and ERC20 contract-address rewriting).

The final v1.2 Track-B configs keep RESTgym on the historical host `9090`. The retained workload fixture emits the P2S primitive-trace schema, `p2s record` freezes that file via `research.record_trace_source`, and the shared framework takes over at compilation/evaluation.

This keeps the target environment closer to the original experiment while still eliminating the old Track-B P2S compiler/evaluator wrapper.

## AutoRestTest discrepancy resolution

The final-run source of truth is:

```text
AutoRestTest LLM = DeepSeek-V4-Flash
```

The archived local-base-Qwen template remains preserved because it documents an earlier setup stage, but v1.2 does not use it for final-result reproduction.
