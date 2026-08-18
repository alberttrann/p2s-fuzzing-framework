# Getting Started with P2S Framework v1.2

This guide is for a first-time user who has cloned/downloaded the repository and wants to answer three questions:

1. **How do I install P2S correctly?**
2. **What else do I need before it can actually run against an API?**
3. **What is the first end-to-end workflow I should execute?**

P2S is a research/security-testing framework. Use it only on local, disposable, or explicitly authorized targets.

---

## 1. Install and verify P2S

### Path A — wheel installation

If you downloaded the release bundle, start in its root:

```text
p2s_framework_sdk_release_v1.2.0_framework_native_final/
├── dist/
│   └── p2s_framework-1.2.0-py3-none-any.whl
└── source/
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it:

```bash
# Windows Git Bash
source .venv/Scripts/activate

# Windows PowerShell
# .venv\Scripts\Activate.ps1

# Windows cmd
# .venv\Scripts\activate.bat

# Linux/macOS
# source .venv/bin/activate
```

Install:

```bash
python -m pip install --upgrade pip
python -m pip install ./dist/p2s_framework-1.2.0-py3-none-any.whl
```

Verify:

```bash
python -c "import p2s; print(p2s.__version__)"
p2s --help
```

Expected:

```text
1.2.0
```

### Path B — source/editable installation

If you cloned the repository, `cd` into the directory containing `pyproject.toml`:

```bash
cd /path/to/p2s-framework
python -m venv .venv
source .venv/Scripts/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

Now edits to `p2s/` are immediately used by the environment.

For development:

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
```

---

## 2. What installation does *not* provide

`pip install` gives you the Python package and its Python dependencies. It does **not** automatically create a target API, OpenAPI spec, state reset environment, or LLM server.

For a real P2S run you normally need:

### A. A target API

A local/Dockerized/authorized application that P2S may execute requests against.

### B. OpenAPI / Swagger

P2S grounds the recorded HTTP workflow against the API contract.

### C. OCLI (default research executor)

```bash
npm install -g openapi-to-cli
ocli --help
```

This requires Node.js/npm.

### D. A mutation model

For example, an OpenAI-compatible local server:

```text
http://localhost:8081/v1
```

The public P2S Q8_0 model can be served through llama.cpp; see [`MODEL_AND_TRAINING.md`](MODEL_AND_TRAINING.md).

### E. State restoration

Choose what matches the target:

```text
PostgreSQL template snapshot
Docker restart
Mongo dump/restore
file restore
arbitrary reset command
stateless
```

### F. Target repository/workload fixtures for research reproduction

Only needed if reproducing AITasker, SEAL Track A, or RESTgym Track B.

---

## 3. Use P2S on your own API

The fastest way to understand P2S is to configure one known-good business flow on an API you control.

### Step 1 — create a working directory

```bash
mkdir -p runs/my-api
```

### Step 2 — create `my_api.toml`

Start with:

```toml
[target]
name = "my_api"
base_url = "http://localhost:8080/api"
openapi_spec = "openapi.json"
state_adapter = "docker"
executor_adapter = "ocli"
golden_out = "my_api_golden_dataset.jsonl"
silver_out = "my_api_silver_dataset.jsonl"
checkpoint_file = "my_api_processed_flows.txt"

[llm]
backend = "openai_compat"
base_url = "http://localhost:8081/v1"
model = "my-model"
api_key = "no-key"
max_attempts = 6

[ocli]
profile_name = "my_api"
api_base_url = "http://localhost:8080/api"
openapi_spec = "openapi.json"

[docker]
container_name = "my_api"
restart_sleep_seconds = 3.0

[proxy]
listen_port = 8090
target_host = "http://localhost:8080"
flow_strategy = "header"
flow_header = "X-Flow-ID"
output_file = "primitive_traces.jsonl"
```

Change the URLs, container, and model to your environment.

For non-Docker targets, use another state adapter; see [`CONFIGURATION_REFERENCE.md`](CONFIGURATION_REFERENCE.md).

### Step 3 — run preflight

```bash
p2s doctor -c my_api.toml --workdir runs/my-api
```

Fix every `[FAIL]` before a long run.

### Step 4 — make sure your target is running

If your config contains research launch commands, use:

```bash
p2s prepare -c my_api.toml --workdir runs/my-api
```

Otherwise launch the target yourself.

### Step 5 — record one valid workflow

Start the proxy in Terminal A:

```bash
p2s proxy -c my_api.toml --workdir runs/my-api
```

Exercise a valid business flow through the proxy in Terminal B. If you use explicit flow IDs, add the configured `X-Flow-ID` header to every request belonging to the same flow.

The target traffic should go through the proxy port, while the proxy forwards to the real API.

You should obtain:

```text
runs/my-api/primitive_traces.jsonl
```

If the target's existing workload fixture already emits P2S primitive traces, configure `research.record_trace_source` instead and use `p2s record`.

### Step 6 — compile against OpenAPI

```bash
p2s compile -c my_api.toml --workdir runs/my-api
```

Inspect:

```text
runs/my-api/compiled_traces.jsonl
runs/my-api/ocli_catalog.json
```

Do not continue if the important operations failed to ground.

### Step 7 — prove the model endpoint works

Before fuzzing, verify the configured LLM server is reachable and uses the intended model.

A local llama.cpp research endpoint is typically:

```text
http://localhost:8081/v1
```

### Step 8 — run a short evaluation first

```bash
p2s fuzz -c my_api.toml --workdir runs/my-api --time-budget 120
```

Start with minutes, not hours. Confirm:

- state resets succeed;
- prefix replay establishes prerequisites;
- generated commands reach the API;
- Golden/Silver JSONL is produced;
- the target survives reset/repetition.

### Step 9 — inspect outputs

Typical files:

```text
runs/my-api/
├── primitive_traces.jsonl
├── compiled_traces.jsonl
├── ocli_catalog.json
├── my_api_golden_dataset.jsonl
├── my_api_silver_dataset.jsonl
├── my_api_processed_flows.txt
├── *_execution_log.txt
└── *_run_metadata.json
```

A Golden is a **candidate**. It needs semantic validation before you call it a verified security vulnerability.

---

## 4. Python equivalent

```python
from p2s import P2S

sdk = P2S.from_toml("my_api.toml", workdir="runs/my-api")

issues = sdk.doctor()
if issues:
    raise RuntimeError("\n".join(issues))

sdk.prepare()
sdk.record()
sdk.compile()
fuzzer = sdk.fuzz(time_budget_seconds=120)
print(fuzzer.metrics)
sdk.cleanup()
```

See the root [`SDK_GUIDE.md`](../SDK_GUIDE.md) for the full API.

---

## 5. Reproduce the research instead

If your goal is not a custom target but the full study, do **not** invent a new config. Use the checked-in research profiles.

Set the relevant roots:

```bash
export AITASKER_ROOT=/path/to/AITasker
export SEAL_ROOT=/path/to/SWP391_SealHackathon_BackEnd
export RESTGYM_ROOT=/path/to/restgym
```

Then follow:

1. [`REPRODUCIBILITY.md`](REPRODUCIBILITY.md)
2. [`TRACK_A_WITH_P2S_FRAMEWORK.md`](TRACK_A_WITH_P2S_FRAMEWORK.md)
3. [`TRACK_B_WITH_P2S_FRAMEWORK.md`](TRACK_B_WITH_P2S_FRAMEWORK.md)
4. [`MODEL_AND_TRAINING.md`](MODEL_AND_TRAINING.md)

The canonical docs use one P2S v1.2 implementation. The exact historical scripts are retained separately under `original_reporducibility_docs/` for audit fidelity.

The completed original AutoRestTest Track-A experiment used **DeepSeek-V4-Flash**.

---

## 6. Common first-time mistakes

### Running `pip install -e .` from the wrong directory

The current directory must contain:

```text
pyproject.toml
p2s/
```

### Thinking the wheel includes OCLI

It does not. OCLI is a Node.js tool:

```bash
npm install -g openapi-to-cli
```

### Starting fuzzing before compiling a valid trace

Always inspect the baseline trace and compiled trace first.

### Using a state reset that destroys required fixtures

The reset primitive must recreate the *same usable test state*, not merely restart a process.

### Treating every Golden as a vulnerability

Do not. Track A applies semantic verification; Track B's standardized FD view is 5xx-only.

### Mixing run directories

Use a separate `--workdir` for each target/model/repetition.

---

## 7. Where to go next

- Framework concepts/results: root [`README.md`](../README.md)
- Python API: [`SDK_GUIDE.md`](../SDK_GUIDE.md)
- TOML fields: [`CONFIGURATION_REFERENCE.md`](CONFIGURATION_REFERENCE.md)
- Research reproduction: [`REPRODUCIBILITY.md`](REPRODUCIBILITY.md)
- Packaging: [`BUILD_AND_RELEASE.md`](BUILD_AND_RELEASE.md)
