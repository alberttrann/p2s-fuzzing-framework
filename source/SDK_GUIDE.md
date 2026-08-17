# P2S Python SDK

P2S is installable as a normal Python package and exposes both a Python SDK and the original CLI workflow.

## Install

From a source checkout:

```bash
python -m pip install .
```

Editable development install:

```bash
python -m pip install -e ".[dev]"
```

Local Transformers backend:

```bash
python -m pip install ".[transformers]"
```

## Programmatic API

```python
from p2s import P2S

p2s = P2S.from_toml("configs/aitasker.toml", workdir="runs/aitasker")

# Capture traffic (blocking server)
# p2s.run_proxy()

# Compile proxy traces into OCLI traces and catalog
compiled, catalog = p2s.compile()

# Execution-verified evaluation
fuzzer = p2s.fuzz()
print(fuzzer.metrics)

# Teacher-Critic training corpus generation
p2s.generate_data()

# Build the final stratified SFT dataset
training_file = p2s.prepare_dataset()
print(training_file)
```

### Non-blocking proxy ownership

For an application that wants to own the server lifecycle:

```python
server = p2s.create_proxy_server(host="127.0.0.1")
# Run server.serve_forever() in your own thread/process/event lifecycle.
```

## Low-level APIs

The original components remain importable for custom integrations:

```python
from p2s.compiler.compiler import P2SCompiler
from p2s.engine.fuzzer import P2SFuzzer
from p2s.engine.generator import P2SDataGenerator
from p2s.engine.adapters.executor import OcliExecutorAdapter, RawHttpExecutorAdapter
from p2s.engine.adapters.llm_adapter import OpenAICompatAdapter, TransformersAdapter
from p2s.engine.adapters.state_adapter import PostgresTemplateAdapter, StatelessAdapter
```

## CLI

The CLI is now packaged from `p2s.cli` and uses the same SDK facade:

```bash
p2s compile -c configs/aitasker.toml
p2s fuzz -c configs/aitasker.toml
p2s generate-data -c configs/aitasker.toml
p2s prepare-dataset -c configs/aitasker.toml
```

`python -m p2s ...` is equivalent.

## Public API contract

Stable top-level imports in 1.1:

- `P2S` / `P2SClient`
- `P2SConfig`, `TargetConfig`, `LLMConfig`, `ProxyConfig`, `PostgresConfig`
- `load_config`
- `P2SError`, `P2SConfigurationError`
- `patch_openapi_required`

Advanced engine modules remain importable but should be treated as lower-level APIs.
