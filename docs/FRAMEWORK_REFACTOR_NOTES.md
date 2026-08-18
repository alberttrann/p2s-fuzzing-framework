# Framework-Native Reproduction Refactor Notes

P2S v1.2 separates **historical implementation preservation** from the **maintained reproduction path**.

## Directory contract

```text
docs/
    maintained reproduction using one P2S framework implementation

original_reporducibility_docs/
    frozen historical/original procedures, helper scripts, and audits
```

The spelling `original_reporducibility_docs/` is intentionally retained because it is the repository directory name chosen for this refactor.

## What moved into the framework

The maintained path no longer asks researchers to switch between slightly different copies of P2S proxy/compiler/evaluator code for AITasker, SEAL Track A, and RESTgym Track B. The shared package now provides:

- configurable trace capture and flow-boundary handling;
- one JSON/YAML OpenAPI compiler with context-path, form-urlencoded, and opaque-body support;
- one execution-verified fuzzing engine with configurable prefix replay, reset timing, cyclic wall-clock budgets, and guarded 2xx candidate logic;
- PostgreSQL, Docker, MongoDB, file, stateless, and arbitrary-command state adapters;
- declarative source-file patches and lifecycle commands for benchmark preparation;
- OpenAPI acquisition/sanitization and controlled test credential acquisition;
- framework-native strict 5xx filtering-before-dedup for Track-B FD accounting.

## What remains target-specific

Valid business workflows and benchmark fixtures remain target-specific: AITasker mainflows, the SEAL business-flow driver, RESTgym per-service workload recorders, SQL seeds/migrations, and the target applications themselves. These define **valid application state**, not a private P2S implementation.

## AutoRestTest source-of-truth resolution

The completed original Track-A AutoRestTest experiment used **DeepSeek-V4-Flash**. Any older archived local-base-Qwen AutoRestTest configuration is preserved only as historical development evidence and is not the final-run reproduction configuration.
