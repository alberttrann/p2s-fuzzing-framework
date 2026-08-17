# P2S Framework

**Execution-Verified API Security Fuzzing via Stateful Self-Play**

P2S (**Primitive-to-Semantics**) turns real API traffic into state-aware security probes, executes every mutation against the live backend, and uses the backend response as the oracle for both **security evaluation** and **specialist training-data generation**.

Instead of fuzzing isolated endpoints, P2S preserves the business-flow history that made the target request reachable: authenticated identities, created resources, lifecycle state, and prior API actions. Captured traffic is compiled into OpenAPI-grounded OCLI primitives, mutated by an LLM, executed inside a resettable target state, and recorded as execution-verified outcomes.

> **Research result:** the P2S specialist roughly doubled the verified kill rate of its architecturally identical untuned Qwen3.5-9B control on an independent 128-endpoint backend, while standardized RESTgym evaluation showed high fault yield despite comparatively low source-code coverage.

---

## Results at a glance

### Track A — independent SEAL backend

P2S was trained on **AITasker** and evaluated zero-shot on the independently developed **SEAL Hackathon backend** (Spring Boot / Java, 128 REST endpoints, 21 stateful business flows).

| System | Executed records | Verified TPs | Unique verified signatures | Verified kill rate | M1 syntax pass |
|---|---:|---:|---:|---:|---:|
| **P2S fine-tuned** | 1,075 | **31** | **30** | **2.9%** | **99.9%** |
| DeepSeek-V4-Flash | 1,094 | 26 | 26 | 2.4% | 95.8% |
| Base Qwen3.5-9B | 1,122 | 16 | 16 | 1.4% | 99.4% |

The fine-tuned P2S model achieved about **2.02× the verified kill rate of the untuned Qwen control**, including **24 verified server faults and 7 verified security bypasses**.

Conventional black-box tools were also audited on the same backend. AutoRestTest, CATS, and Schemathesis produced substantial native failure volumes, but those counters were not treated as security findings without post-hoc evidence of an unauthorized action, data exposure, or invalid state transition.

### Track B — SBFT 2026 RESTgym

P2S was then run for one hour on each of the **11 RESTgym services** used by the SBFT 2026 REST League (**317 documented operations**).

Across the eleven services, P2S produced:

- **321** strict status-aligned unique 5xx signatures
- **29.18 faults/API**
- **25.55 operations/API** trace-derived operation coverage estimate
- **14.46%** mean branch coverage
- **27.37%** mean line coverage
- **29.07%** mean method coverage

In the paper's clearly labeled **seven-system counterfactual recomputation** using the official final-metric score formula, P2S ranks **2nd in Fault Detection** and **2nd in Effectiveness** among eligible tools. This is **not an official SBFT competition ranking**: the P2S runs use one repetition per service and do not include the native Restats time-series required for official AUC/Roadrunner scoring.

The notable result is the rank inversion: **high fault yield despite low structural coverage**. P2S ranks near the bottom in source coverage while remaining near the top in status-aligned fault detection, supporting the paper's distinction between *structural breadth* and *semantic security depth*.

---

## How P2S works

```text
Live API traffic
      │
      ▼
┌──────────────────────┐
│ Transparent Proxy    │  → primitive_traces.jsonl
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ Trace Compiler       │  → compiled_traces.jsonl
│ + OpenAPI grounding  │  → OCLI catalog
└──────────┬───────────┘
           ▼
┌──────────────────────────────┐
│ Stateful P2S Engine          │
│ • replay prior flow steps    │
│ • mutate target primitive    │
│ • execute against backend    │
│ • restore isolated state     │
└──────────┬───────────────────┘
           ▼
     execution oracle
       ┌──────┴──────┐
       ▼             ▼
   Golden          Silver
 exploit/fault   defended boundary
       └──────┬──────┘
              ▼
   SFT corpus / evaluation
```

P2S uses a **15-vector security taxonomy** spanning malformed inputs, boundary attacks, IDOR/BOLA/BFLA, mass assignment, business-flow bypass, replay/idempotency, context desynchronization, and premature lifecycle progression.

The key design principle is simple: **the backend—not another LLM—is the label oracle**.

---

## Install

From the release wheel:

```bash
pip install p2s_framework-1.1.0-py3-none-any.whl
```

For local development:

```bash
git clone <your-p2s-repository>
cd p2s-framework
pip install -e .
```

Verify:

```bash
p2s --help
```

Python 3.10+ is required.

---

## Python SDK

```python
from p2s import P2S

p2s = P2S.from_toml(
    "configs/target.toml",
    workdir="runs/target",
)

# Captured HTTP traces -> OpenAPI-grounded executable primitives
compiled_traces, catalog = p2s.compile()

# Execution-verified evaluation
fuzzer = p2s.fuzz()

# Self-play training-data generation
p2s.generate_data()

# Deduplicate + stratify Golden/Silver records
p2s.prepare_dataset()
```

The SDK also exposes builders for state, execution, and LLM adapters when integrating P2S into a larger testing system.

---

## CLI

```bash
# 1. Capture real API traffic
p2s proxy --config configs/target.toml

# 2. Compile traces against OpenAPI
p2s compile --config configs/target.toml

# 3a. Evaluate a model
p2s fuzz --config configs/target.toml

# 3b. Or generate execution-verified SFT data
p2s generate-data --config configs/target.toml

# 4. Build the final corpus
p2s prepare-dataset --config configs/target.toml
```

Post-hoc analysis:

```bash
p2s verify
p2s analyze
p2s reclassify
p2s m1
```

---

## Adapters

P2S is designed to move between unrelated APIs without rewriting the engine.

**State restoration**

- PostgreSQL `CREATE DATABASE ... WITH TEMPLATE`
- MongoDB dump/restore
- file-backed state
- Docker restart
- stateless targets

**Execution**

- OCLI
- raw HTTP

**LLM backends**

- OpenAI-compatible endpoints (including llama.cpp / LM Studio / compatible hosted APIs)
- local Hugging Face Transformers models

Target-specific behavior lives primarily in TOML configuration and optional setup hooks.

---

## Training-data result

The original AITasker self-play run produced:

| Dataset stage | Records |
|---|---:|
| Raw Silver | 1,917 |
| Deduplicated Silver | 1,782 |
| Unique Golden | 44 |
| Final stratified SFT corpus | 2,266 |

Only **44 unique exploit-confirmed examples** survived deduplication from a heavily defended modern backend. After execution-grounded fine-tuning, that small Golden set was sufficient for the resulting specialist to outperform the untuned control on the independent SEAL target.

---

## Metrics

P2S reports complementary dimensions rather than reducing API security testing to request counts or coverage alone.

- **M1 — Syntax Pass Rate:** did the generated primitive reach the API rather than fail in the CLI/parser layer?
- **M2 — Boundary Prediction:** did the model correctly predict the backend's response boundary?
- **M3 / verified fault yield:** how often did executed probes produce candidate or post-hoc verified faults/security outcomes?

For research comparisons, raw 5xx counts and verified semantic security findings should be reported separately.

---

## Research artifacts

This repository is the **reusable P2S framework / SDK**. The full research project contains additional artifact packages that should remain separate from the installable library:

- **AITasker training artifact** — proxy/compiler runs, primitive and compiled traces, Golden/Silver JSONL, final SFT JSONL, training notebook
- **Track A / SEAL artifact** — P2S fine-tuned, base Qwen and DeepSeek runs plus AutoRestTest, CATS and Schemathesis evidence
- **Track B / RESTgym artifact** — P2S runs across all 11 SBFT services plus per-service `code-coverage.csv`
- **Model releases** — LoRA, merged 4-bit, merged 16-bit, and GGUF F16/Q8_0 exports
- **AutoRestTest-SEAL artifact** — SEAL-specific AutoRestTest inputs and generated run data

This separation keeps `pip install p2s-framework` lightweight while preserving complete experimental reproducibility in dedicated releases.

---

## Reproduce the research

The complete paper-level reproduction path is documented in **[`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md)**. It covers:

- AITasker trace capture, execution-verified Golden/Silver generation, stratified SFT corpus construction, and fine-tuning;
- downloading the published LoRA / merged checkpoints / GGUF artifacts and serving the P2S Q8_0 model with `llama.cpp`;
- Track A P2S, base-Qwen, and DeepSeek evaluation on SEAL plus verified-Golden post-hoc processing;
- the independent AutoRestTest, CATS, and Schemathesis Track A baseline runs; and
- the full 11-service RESTgym Track B protocol, including target-specific reset adapters and JaCoCo collection.

The guide also separates **historical-parity commands** from the normalized v1.1.0 SDK path and flags stale draft settings that should not be used to reproduce the final paper.

---

## Documentation

- [`SDK_GUIDE.md`](SDK_GUIDE.md) — SDK usage and integration
- [`docs/P2S_FRAMEWORK_REFERENCE.md`](docs/P2S_FRAMEWORK_REFERENCE.md) — full implementation reference
- [`CHANGELOG.md`](CHANGELOG.md) — release history

Research paper:

> **P2S: Primitive-to-Semantics Training for Execution-Verified API Security Fuzzing via Self-Play and Specialist LLM Adaptation**

---

## Responsible use

P2S generates adversarial API mutations and should only be used against systems you own or are explicitly authorized to test. Run experiments in isolated environments with disposable state and non-production credentials.

---

## Release

**v1.1.0 — first public P2S Python SDK release**
