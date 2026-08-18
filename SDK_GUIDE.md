# P2S Python SDK v1.2 — First-User and Developer Guide

P2S exposes one implementation through two interfaces:

```text
Python API                       CLI
----------                       ---
P2S.from_toml(...)      <=>      p2s <mode> -c config.toml
sdk.prepare()            <=>      p2s prepare
sdk.record()             <=>      p2s record
sdk.compile()            <=>      p2s compile
sdk.fuzz()               <=>      p2s fuzz
```

The SDK is intentionally configuration-driven. You normally **do not subclass the fuzzer for each target**. Instead, target-specific facts—URLs, patches, auth, reset commands, OpenAPI handling, workload commands, and model endpoints—live in TOML.

If you are completely new to the project, read [`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md) first. This file explains the API in more depth.

---

## 1. Installation

### Install from a wheel

From a release bundle:

```bash
python -m venv .venv
source .venv/Scripts/activate      # Git Bash / Windows
# source .venv/bin/activate        # Linux/macOS

python -m pip install --upgrade pip
python -m pip install ./dist/p2s_framework-1.2.0-py3-none-any.whl
```

Verify:

```bash
python -c "import p2s; print(p2s.__version__)"
p2s --help
```

### Install from source

Run this from the repository directory that contains `pyproject.toml`:

```bash
python -m venv .venv
source .venv/Scripts/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

For development/testing:

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
```

Optional local Transformers inference:

```bash
python -m pip install -e ".[transformers]"
```

### External runtime tools

Installing the wheel installs Python dependencies, but a research run may also need:

- a running target API;
- its OpenAPI/Swagger document;
- Node.js + OCLI for the default research executor;
- an OpenAI-compatible LLM endpoint or optional Transformers backend;
- PostgreSQL, Docker, MongoDB, or another reset primitive selected by the config.

OCLI is separate because it is not a Python package:

```bash
npm install -g openapi-to-cli
ocli --help
```

---

## 2. The P2S mental model

A P2S run has six conceptual stages:

```text
1. PREPARE TARGET
   patches / launch / readiness / OpenAPI / auth
               ↓
2. RECORD VALID WORKFLOW
   stateful requests + observed responses
               ↓
3. COMPILE
   HTTP trace → OpenAPI-grounded executable OCLI trace
               ↓
4. RESTORE STATE
   recreate the prerequisite state for each mutation
               ↓
5. MUTATE + EXECUTE
   LLM mutation → live target response
               ↓
6. ANALYZE
   Golden/Silver candidates → verification/dedup/metrics
```

The important design rule is that the **live target is the execution signal**. The model proposes a mutation; P2S executes it and records what actually happened.

---

## 3. The smallest useful Python program

```python
from p2s import P2S

sdk = P2S.from_toml(
    "configs/research/track_a_seal_p2s.toml",
    workdir="runs/track-a/p2s",
)

issues = sdk.doctor()
if issues:
    for issue in issues:
        print("[FAIL]", issue)
    raise SystemExit(2)

sdk.prepare()
sdk.record()
compiled, catalog = sdk.compile()
fuzzer = sdk.fuzz()
print(fuzzer.metrics)
sdk.coverage()
sdk.cleanup()
```

`workdir` is where runtime artifacts are written. Keeping every repetition in a separate directory avoids mixing model outputs or stale traces.

---

## 4. Loading configuration

The recommended entry point is:

```python
sdk = P2S.from_toml("path/to/config.toml", workdir="runs/example")
```

You can also construct `P2SConfig` yourself, but TOML is preferred for experiments because it is inspectable and versionable.

Useful top-level imports:

```python
from p2s import (
    P2S,
    P2SClient,
    P2SConfig,
    TargetConfig,
    LLMConfig,
    ProxyConfig,
    PostgresConfig,
    DockerConfig,
    MongoConfig,
    FileStateConfig,
    CommandStateConfig,
    OcliConfig,
    OpenAPISetupConfig,
    AuthConfig,
    ResearchConfig,
    PatchConfig,
    load_config,
    P2SError,
    P2SConfigurationError,
    patch_openapi_required,
)
```

The full TOML schema is documented in [`docs/CONFIGURATION_REFERENCE.md`](docs/CONFIGURATION_REFERENCE.md).

---

## 5. Lifecycle methods

### `doctor()`

```python
issues = sdk.doctor()
```

Returns a list of configuration/environment problems. An empty list means the framework did not find a preflight issue.

Typical uses:

- missing configured target root;
- missing required environment variable;
- missing reset command;
- unavailable prerequisite file/path.

Run it before a long experiment.

CLI:

```bash
p2s doctor -c config.toml --workdir runs/example
```

### `patch()`

```python
sdk.patch()
```

Applies configured idempotent research patches. Examples from the public profiles include enabling RESTgym services, changing the Flight Search benchmark identity from USER to ADMIN, or applying target-side compatibility fixes.

CLI:

```bash
p2s patch -c config.toml
```

### `fetch_openapi()`

```python
path = sdk.fetch_openapi()
```

Fetches and sanitizes the OpenAPI document according to `[openapi_setup]`.

This can include operations such as:

- setting the correct server URL;
- removing destructive logout/self-delete operations from a baseline contract;
- writing the fetched document to a stable local path.

### `acquire_auth()`

```python
sdk.acquire_auth()
```

Obtains the configured controlled test credential and persists/exports it according to the profile.

Credentials should come from environment variables or controlled test accounts. Do not commit production secrets.

### `prepare()`

```python
sdk.prepare()
```

The normal high-level setup call. It performs the configured combination of:

```text
patches
→ target prepare/launch commands
→ readiness checks
→ OpenAPI fetch/sanitization
→ auth acquisition
```

You can call the smaller lifecycle methods individually when debugging.

### `record()`

```python
sdk.record()
```

Runs the configured workload and freezes a baseline primitive trace.

Two trace modes are supported:

1. **P2S proxy output** — normal custom-target path;
2. **workload-produced P2S trace** — used by RESTgym profiles so RESTgym's own mitmproxy stays semantically active for auth/request rewriting.

The result is normally:

```text
primitive_traces.jsonl
```

or the configured snapshot filename.

### `coverage()`

```python
sdk.coverage()
```

Runs the target-specific coverage collection command when configured. Track B uses this for JaCoCo extraction.

### `cleanup()`

```python
sdk.cleanup()
```

Executes configured cleanup commands. Put destructive cleanup only in controlled test profiles.

---

## 6. Trace capture

### Run the P2S proxy directly

```python
sdk.run_proxy()
```

This is blocking and normally runs in its own terminal/process.

CLI:

```bash
p2s proxy -c config.toml --workdir runs/example
```

The proxy can preserve flow identity using endpoint-derived boundaries or an explicit header such as `X-Flow-ID`.

A primitive trace record contains the business-flow identity, step order, request, and observed response. Sensitive headers such as authorization/cookies can be masked before persistence.

### When *not* to replace the benchmark proxy

RESTgym Track B is the key example. Its mitmproxy sometimes performs experiment semantics (session auth or address rewriting), so the canonical v1.2 reproduction keeps that proxy and has `p2s record` freeze a workload-produced P2S trace instead.

---

## 7. Compile: trace → OpenAPI-grounded executable operations

```python
compiled, catalog = sdk.compile()
```

Typical outputs:

```text
compiled_traces.jsonl
ocli_catalog.json
```

The compiler supports JSON/YAML OpenAPI, context-path normalization, path/query/body parameters, request-body schemas, and form-urlencoded bodies.

CLI:

```bash
p2s compile -c config.toml --workdir runs/example
```

If compilation misses operations, inspect:

1. the captured request path;
2. the OpenAPI server/base path;
3. context-path stripping config;
4. whether the operation actually exists in the fetched spec.

---

## 8. State adapters

P2S restores a controlled baseline before mutation attempts so a deep target step is tested in the state that makes it meaningful.

The high-level SDK chooses the adapter from `target.state_adapter`.

### PostgreSQL template snapshot

```python
from p2s.engine.adapters.state_adapter import PostgresTemplateAdapter
```

Used by the original P2S self-play/Track-A lineage. Supports active DB recreation, seed command, post-seed commands, and optional setup hook.

### Docker restart

```python
from p2s.engine.adapters.state_adapter import DockerRestartAdapter
```

Useful for in-memory/H2/embedded stores where restart reproduces the known initial state.

### MongoDB dump/restore

```python
from p2s.engine.adapters.state_adapter import MongoDumpAdapter
```

### File backup

```python
from p2s.engine.adapters.state_adapter import FileBackupAdapter
```

### Arbitrary command reset

```python
from p2s.engine.adapters.state_adapter import CommandStateAdapter
```

Used when the target needs a benchmark-specific reset such as contract redeployment, SQL re-import, topic recreation, or another controlled command.

### Stateless

```python
from p2s.engine.adapters.state_adapter import StatelessAdapter
```

Only use when the target truly does not require mutable state restoration.

---

## 9. Executors

### OCLI executor

```python
from p2s.engine.adapters.executor import OcliExecutorAdapter
```

This is the default research path. P2S grounds the operation against OpenAPI and executes CLI commands through an OCLI profile.

The profile can receive:

- bearer token directly/from env/from file;
- Basic auth directly/from env/from file;
- OpenAPI path/URL;
- target API base URL;
- command prefix;
- throttle and timeout.

### Raw HTTP executor

```python
from p2s.engine.adapters.executor import RawHttpExecutorAdapter
```

Useful when OCLI is not appropriate. Set:

```toml
[target]
executor_adapter = "raw_http"
```

---

## 10. LLM adapters

### OpenAI-compatible endpoint

The research path uses an OpenAI-compatible adapter for local llama.cpp/LM Studio servers and compatible remote APIs.

Conceptual configuration:

```toml
[llm]
backend = "openai_compat"
base_url = "http://localhost:8081/v1"
model = "qwen35-9b-p2s"
api_key = "no-key"
max_attempts = 6
```

For a remote provider, use environment-backed credentials rather than committing an API key.

### Transformers backend

Install:

```bash
python -m pip install -e ".[transformers]"
```

Then configure the local model path/revision supported by the adapter.

---

## 11. Fuzz/evaluate

```python
fuzzer = sdk.fuzz()
print(fuzzer.metrics)
```

CLI:

```bash
p2s fuzz -c config.toml --workdir runs/example
```

Useful CLI overrides:

```bash
p2s fuzz -c config.toml --time-budget 3600 --cyclic
p2s fuzz -c config.toml --no-openapi-patch
```

A run normally produces:

```text
*_golden_dataset.jsonl
*_silver_dataset.jsonl
*_processed_flows.txt
*_execution_log.txt
*_run_metadata.json
```

Interpretation:

- **Golden** = candidate execution-positive outcome;
- **Silver** = defended/expected boundary observation;
- **Golden is not automatically a verified vulnerability**.

For Track A, run the semantic verifier/dedup step before headline claims. For Track B benchmark FD, filter to 5xx before deduplication.

---

## 12. Self-play training-data generation

```python
sdk.generate_data()
dataset = sdk.prepare_dataset()
```

CLI:

```bash
p2s generate-data -c configs/research/aitasker_training.toml --workdir runs/aitasker
p2s prepare-dataset -c configs/research/aitasker_training.toml --workdir runs/aitasker
```

The dataset builder performs content deduplication and the configured Golden oversampling/stratification procedure.

The resulting JSONL is a training artifact. The model-training notebook/Unsloth stack is deliberately outside the installed `p2s` package; see [`docs/MODEL_AND_TRAINING.md`](docs/MODEL_AND_TRAINING.md).

---

## 13. Analytics commands

### Analyze run pairs

```bash
p2s analyze --dir runs/track-a/p2s
```

Finds matching Golden/Silver pairs and prints run summaries.

### Reclassify attack vectors

```bash
p2s reclassify --backend llamacpp --slm-url http://localhost:1234/v1
```

### M1 syntax/execution pass analysis

```bash
p2s m1 --backend llamacpp
```

### Track-A candidate verification

```bash
p2s verify \
  --golden-file llamacpp_golden_dataset_reclassified.jsonl \
  --verified-out seal_p2s_verified_goldens.jsonl
```

### Track-B strict 5xx-before-dedup FD proxy

```bash
p2s fd \
  --golden-file petclinic_p2s_golden_dataset.jsonl \
  --dedup-out petclinic_strict_5xx.jsonl
```

This distinction matters: a 2xx security-intent candidate must not be counted in an SBFT 5xx-only Fault Detection number.

---

## 14. Using P2S on a new authorized target

You need five pieces of target knowledge:

1. **base URL + OpenAPI document**;
2. **representative valid stateful workflow**;
3. **flow-boundary strategy**;
4. **auth/OCLI profile behavior**;
5. **state-reset primitive**.

Recommended procedure:

```text
copy a config template
→ fill [target], [llm], [ocli], [proxy]
→ choose state adapter
→ add [research]/[openapi_setup]/[auth]/[[patches]] only if needed
→ p2s doctor
→ prepare
→ record
→ compile
→ inspect compiled traces
→ fuzz with a short budget
→ validate outputs
→ scale the run
```

Do not start with an hour-long run. First prove that one baseline flow can be recorded, compiled, reset, replayed, and mutated correctly.

See [`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md) for a concrete walkthrough.

---

## 15. Framework-native research reproduction

The canonical maintained reproduction configs are:

```text
configs/research/
├── aitasker_training.toml
├── track_a_baselines.toml
├── track_a_seal_p2s.toml
├── track_a_seal_base_qwen.toml
├── track_a_seal_deepseek.toml
└── track_b/
    ├── blog.toml
    ├── erc20.toml
    ├── features-service.toml
    ├── flight-search.toml
    ├── gestao-hospital.toml
    ├── kafka-rest-proxy.toml
    ├── market.toml
    ├── notebook-manager.toml
    ├── person-controller.toml
    ├── pet-clinic.toml
    └── project-tracking-system.toml
```

Use:

- [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md) for the master workflow;
- [`docs/TRACK_A_WITH_P2S_FRAMEWORK.md`](docs/TRACK_A_WITH_P2S_FRAMEWORK.md) for Track A;
- [`docs/TRACK_B_WITH_P2S_FRAMEWORK.md`](docs/TRACK_B_WITH_P2S_FRAMEWORK.md) for Track B.

The historical one-off scripts remain under `original_reporducibility_docs/` for audit fidelity, not as the primary SDK path.

The completed original AutoRestTest Track-A run used **DeepSeek-V4-Flash**.

---

## 16. Error handling

```python
from p2s import P2SError, P2SConfigurationError

try:
    sdk.prepare()
except P2SConfigurationError as exc:
    print("configuration problem:", exc)
except P2SError as exc:
    print("P2S runtime problem:", exc)
```

Common causes:

- a configured file path is relative to a different root than expected;
- a reset command environment variable is unset;
- OCLI is not installed/on `PATH`;
- model endpoint is not running;
- OpenAPI path/server prefix does not match captured routes;
- target is not ready before recording;
- old run artifacts are being reused unintentionally.

---

## 17. Troubleshooting checklist

### `p2s` command not found

Make sure the virtual environment is activated and the package installed:

```bash
python -m pip show p2s-framework
python -m p2s --help
```

If `python -m p2s` works but `p2s` does not, your shell has not refreshed the environment's scripts path.

### OCLI command not found

```bash
npm install -g openapi-to-cli
ocli --help
```

### `doctor` reports missing target root

Export the root expected by the research config, for example:

```bash
export SEAL_ROOT=/path/to/SWP391_SealHackathon_BackEnd
export RESTGYM_ROOT=/path/to/restgym
export AITASKER_ROOT=/path/to/AITasker
```

### model connection fails

Check the configured `[llm].base_url` directly and verify the server exposes an OpenAI-compatible API.

### compiled operation count looks wrong

Inspect the live OpenAPI and context-path handling before blaming the LLM. The compiler cannot ground an operation that is absent/mismatched in the spec.

### stateful mutation produces nonsense because prerequisites are missing

Verify the state adapter and prefix replay policy. A deep step is only meaningful when the prerequisite state has actually been reconstructed.

---

## 18. Development and package builds

Development install:

```bash
python -m pip install -e ".[dev]"
```

Tests:

```bash
python -m compileall -q p2s tests
python -m pytest -q
```

Build distributions:

```bash
python -m build
```

Generated directories:

```text
build/      temporary build workspace
dist/       wheel/sdist outputs
*.egg-info/ generated package metadata
```

These are not the source of the framework and can be deleted/regenerated. See [`docs/BUILD_AND_RELEASE.md`](docs/BUILD_AND_RELEASE.md).

---

## 19. Low-level APIs

Advanced users can instantiate components directly:

```python
from p2s.compiler.compiler import P2SCompiler
from p2s.engine.fuzzer import P2SFuzzer
from p2s.engine.generator import P2SDataGenerator
from p2s.engine.adapters.executor import OcliExecutorAdapter, RawHttpExecutorAdapter
from p2s.engine.adapters.llm_adapter import OpenAICompatAdapter, TransformersAdapter
from p2s.engine.adapters.state_adapter import (
    PostgresTemplateAdapter,
    DockerRestartAdapter,
    MongoDumpAdapter,
    FileBackupAdapter,
    CommandStateAdapter,
    StatelessAdapter,
)
```

Prefer the `P2S` facade unless you specifically need to embed a component in another harness. The facade is where configuration resolution and research lifecycle behavior are kept consistent.
