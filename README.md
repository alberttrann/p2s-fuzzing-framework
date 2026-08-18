# P2S — Primitive-to-Semantics

> **Deep-State REST API Security Testing Beyond Code Coverage**

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Release](https://img.shields.io/badge/release-v1.2.0-4c1)
![Research](https://img.shields.io/badge/artifact-reproducible-purple)
![OpenAPI](https://img.shields.io/badge/interface-OpenAPI%20%2B%20OCLI-orange)

**P2S (Primitive-to-Semantics)** is an execution-grounded framework for stateful REST API security testing. It captures successful multi-step API traces, grounds them against an OpenAPI specification, converts them into executable OCLI primitives, reconstructs the prerequisite business state before each target request, and asks an LLM to generate fault-seeking mutations. Those mutations are executed against a resettable backend, so the **live system response—not another model—is the external execution signal** used for self-play data generation and evaluation.

The project focuses on security behaviors whose meaning depends on **identity, ownership, lifecycle state, prior requests, and business-flow history**. A request can be syntactically valid and reach the same code path as a legitimate request while still violating a security invariant—for example, modifying another user's resource, progressing an object before prerequisites are met, or exercising a privileged transition in the wrong state.

This repository contains **P2S Framework v1.2.0**, the unified public Python SDK extracted from the research implementation. The original experiments evolved through several one-off proxy/compiler/evaluator scripts; v1.2 moves those differences into declarative research profiles so the maintained reproduction path uses one shared implementation.

> **Public validation source.** The manuscript is still under anonymous review and is therefore not published in this repository. This README intentionally carries the project motivation, experimental design, headline results, limitations, model information, and reproduction entry points needed to validate the work publicly. The manuscript uses anonymized names **SourceMarket** and **HackathonBench**; the public artifacts correspond to **AITasker** and the **SEAL Hackathon backend**.


## Start here — which path do you need?

| Goal | Start here |
|---|---|
| **I only want to install P2S and see that it works** | [First-time setup](docs/GETTING_STARTED.md#1-install-and-verify-p2s) |
| **I want to use P2S on my own authorized API** | [Your first target](docs/GETTING_STARTED.md#3-use-p2s-on-your-own-api) + [configuration reference](docs/CONFIGURATION_REFERENCE.md) |
| **I want to reproduce the full research experiment** | [Framework-native reproduction](docs/REPRODUCIBILITY.md) |
| **I want Track A only** | [Track A with P2S Framework](docs/TRACK_A_WITH_P2S_FRAMEWORK.md) |
| **I want the 11-service RESTgym Track B** | [Track B with P2S Framework](docs/TRACK_B_WITH_P2S_FRAMEWORK.md) |
| **I want to inspect exactly what the historical experiments used** | [`original_reporducibility_docs/`](original_reporducibility_docs/README.md) |
| **I want to develop or rebuild the package** | [Build and release guide](docs/BUILD_AND_RELEASE.md) |

A useful mental model is:

```text
install P2S
   ↓
choose/create a TOML profile
   ↓
p2s doctor
   ↓
prepare target → record a valid stateful workflow → compile against OpenAPI
   ↓
serve/configure an LLM
   ↓
fuzz / generate-data
   ↓
verify / deduplicate / analyze
```

**Installing the package is only the Python part.** To actually fuzz a target, you also need the target API itself, an OpenAPI document, OCLI or the raw-HTTP executor, a configured LLM endpoint for mutation generation, and whichever state-reset dependency your target uses (for example PostgreSQL, Docker, or MongoDB). Research reproduction additionally needs the AITasker, SEAL, or RESTgym target repository described in `docs/`.

---

## TL;DR — what was demonstrated

P2S was trained from execution-grounded self-play on one application and evaluated on unrelated systems and technology stacks.

### Track A — independent deep-state backend

The fine-tuned P2S Qwen3.5-9B specialist was evaluated zero-shot on an independently developed **128-endpoint Spring Boot / PostgreSQL backend with 21 stateful business flows**. The same P2S harness was used for the fine-tuned model, DeepSeek-V4-Flash-3107, and an architecture-matched untuned Qwen3.5-9B control.

| Metric | **P2S Fine-Tuned** | DeepSeek-V4-Flash-3107 | Base Qwen3.5-9B |
|---|---:|---:|---:|
| Executed records | 1,075 | 1,094 | 1,122 |
| Candidate goldens | 48 | 29 | 21 |
| **Validated outcomes** | **31** | 26 | 16 |
| ↳ verified 500 server faults | **24** | 23 | 13 |
| ↳ verified security bypasses | **7** | 3 | 3 |
| Filtered false positives | 17 | 3 | 5 |
| **Unique validated signatures** | **30** | 26 | 16 |
| M1 syntax pass | **99.9%** | 95.8% | 99.4% |
| M2 Silver exact / class | **56.2% / 82.1%** | 15.1% / 68.9% | 29.6% / 79.3% |
| **Validated-outcome rate** | **2.9%** | 2.4% | 1.4% |
| Records / validated outcome ↓ | **34.7** | 42.1 | 70.1 |

In this single-run evaluation, P2S produced approximately **2.02× the validated-outcome rate of the untuned architecture-matched control** and **1.21× that of DeepSeek-V4-Flash-3107**.

The important distinction is that **candidate goldens are not automatically claimed as vulnerabilities**. Track A applies an explicit post-hoc validator before reporting semantic security findings.

### Track B — 11 SBFT 2026 RESTgym services

P2S was also executed for **one hour on each of the 11 RESTgym services used by the SBFT 2026 REST League**, covering **317 documented operations** across heterogeneous stacks and state-reset strategies.

Using a strict **5xx-only, status-aligned deduplication rule** compatible with the construct measured by REST League Fault Detection, the eleven runs produced:

- **321** deduplicated 5xx signatures in total;
- **29.18 signatures/API** on average;
- a numerically higher per-service FD value than the published AutoRestTest ten-run mean on **6/11 services**;
- an equal value on **1/11**;
- a lower value on **4/11**.

Track-B logs additionally contain **55 engine-labeled 2xx bypass candidates**. They are **excluded from the SBFT 5xx Fault Detection number** and are **not claimed as verified vulnerabilities**, because Track B did not apply the same independent semantic verifier used in Track A.

---

## Why P2S exists

Most REST API testing systems are very good at some combination of:

- schema-driven input generation;
- boundary testing;
- malformed-input robustness;
- endpoint / operation exploration;
- dependency inference;
- source-code or branch coverage;
- server-crash discovery.

Those are valuable objectives, but they do not completely describe **semantic security**.

Consider two requests that execute the same controller and service branches:

```text
owner requests /resources/123       -> legitimate 200
foreign user requests /resources/123 -> unauthorized 200
```

The source-code coverage can be identical while the security meaning is different. Conversely, a malformed request can trigger a 500 and increase fault counts without proving an authorization or business-flow violation.

P2S therefore treats the following as complementary rather than interchangeable:

```text
structural coverage
        +
unique 5xx robustness faults
        +
independently adjudicated semantic security outcomes
        +
prerequisite state depth
```

The research frames these dimensions as:

```text
E = < C_struct, F_5xx, S_sem, D_state >
```

where `C_struct` captures structural breadth, `F_5xx` distinct server failures, `S_sem` semantically validated security violations, and `D_state` the prerequisite history required to reach the tested state.

---

# System architecture

P2S consists of five core research components and a reusable analysis layer.

```text
                    ┌──────────────────────────────┐
                    │   Real application traffic   │
                    │ scripts / UI / API clients   │
                    └──────────────┬───────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────┐
                    │  1. Transparent Proxy        │
                    │  capture request + response  │
                    │  preserve flow + step order  │
                    └──────────────┬───────────────┘
                                   │
                         primitive_traces.jsonl
                                   │
                                   ▼
                    ┌──────────────────────────────┐
                    │  2. Trace Compiler           │
                    │  Swagger/OpenAPI grounding   │
                    │  HTTP → executable OCLI      │
                    └──────────────┬───────────────┘
                                   │
               compiled_traces.jsonl + OCLI catalog
                                   │
                                   ▼
          ┌─────────────────────────────────────────────────┐
          │  3. State Adapter / Snapshot Engine             │
          │  recreate prerequisite application state        │
          │  isolate individual mutation attempts           │
          └───────────────────────┬─────────────────────────┘
                                  │
                                  ▼
          ┌─────────────────────────────────────────────────┐
          │  4. P2S Fuzzing / Self-Play Engine              │
          │                                                 │
          │  state history + request + OCLI help + command  │
          │                     ↓                           │
          │                LLM mutation                     │
          │                     ↓                           │
          │                execute live                     │
          │                     ↓                           │
          │              observed outcome                   │
          └───────────────────────┬─────────────────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    ▼                           ▼
           candidate Golden                  Silver
          execution-positive           defended boundary
                    └─────────────┬─────────────┘
                                  │
                                  ▼
                     ┌────────────────────────┐
                     │ 5. Dataset / SFT       │
                     │ dedup + stratification │
                     │ Qwen3.5-9B LoRA        │
                     └────────────┬───────────┘
                                  │
                                  ▼
                           P2S specialist
                                  │
                                  ▼
             Track A semantic validation + Track B benchmark
```

The reusable SDK corresponds to these same architectural units rather than re-implementing a separate simplified pipeline.

---

# 1. Transparent trace capture

`p2s.proxy` sits between the client and target API and records request/response pairs into `primitive_traces.jsonl` while retaining execution ordering.

A primitive record preserves the information needed to reconstruct a business flow:

```json
{
  "flow_id": "flow_project_publish",
  "step": 7,
  "request": {
    "method": "PUT",
    "path": "/projects/123/publish",
    "headers": {"Content-Type": "application/json"},
    "body": {"visibility": "PUBLIC"}
  },
  "response": {
    "status_code": 200,
    "body": {"status": "PUBLISHED"}
  }
}
```

The proxy is intentionally **traffic-source agnostic**. In the research experiments, deterministic shell scripts were used because they make repeated experiments easier, but equivalent traces can be collected from browser interaction or another API client as long as flow boundaries and representative business states are covered.

Sensitive authorization material can be masked in persisted traces and re-injected from the controlled evaluation profile.

Implementation:

```text
p2s/proxy/core_proxy.py
```

---

# 2. OpenAPI-grounded trace compilation

Raw traffic alone is inconvenient as an LLM mutation interface because every API has different URL structures, serialization rules, parameter locations, and authentication conventions.

The P2S trace compiler matches each recorded request against the target OpenAPI document and converts it into an **OCLI command**.

Example:

```text
PUT /users/8eee.../roles
```

becomes an executable primitive such as:

```bash
ocli users_id_roles --id "8eee..." --body '{"roles":["ADMIN"]}'
```

The compiler resolves:

- HTTP method + OpenAPI route matching;
- path parameters;
- query parameters;
- request bodies;
- property-wise vs whole-body serialization;
- bearer-token mapping where appropriate;
- valid command names;
- parameter type / requiredness metadata;
- an OCLI command catalog injected into the model prompt.

The result is an **OpenAPI-to-CLI transfer interface**: unrelated APIs can be exposed to the model using the same command grammar even when their implementation languages and domains differ.

Implementation:

```text
p2s/compiler/compiler.py
```

---

# 3. Resettable state and deep-flow replay

P2S is designed for endpoints that are only meaningful after earlier requests have established valid state.

For a target at flow position `d`, the harness can replay the preceding `d - 1` operations before testing the target mutation.

```text
register client
   ↓
create requirement session
   ↓
complete elicitation stages
   ↓
publish project
   ↓
receive expert bid
   ↓
accept engagement
   ↓
fund milestone
   ↓
submit milestone
   ↓
[MUTATE target action here]
```

Without replaying the valid prefix, a security mutation may be rejected at an earlier prerequisite and never reach the business rule it is intended to challenge.

For PostgreSQL targets, the research implementation uses `CREATE DATABASE ... WITH TEMPLATE` to create and restore snapshots efficiently. The SDK generalizes state restoration behind adapters.

Supported framework adapters include:

- PostgreSQL snapshot/template restoration;
- MongoDB-oriented restoration hooks;
- file-backed state;
- Docker restart-based restoration;
- stateless targets;
- custom reset commands / hooks around research environments.

Implementation:

```text
p2s/engine/adapters/state_adapter.py
```

### Important implementation caveat

The historical evaluator contains a **dirty-state optimization** that may skip restoration after selected 4xx responses under the assumption that those requests were rejected before a durable mutation. HTTP status does not guarantee the absence of side effects. For higher-assurance use, restore after every backend-reaching mutation or verify side-effect absence transactionally.

---

# 4. Stateful mutation generation

For each target primitive, the model receives four key pieces of information:

1. **State history** — the compiled commands that established the current state;
2. **Original request data** — useful values and structure from the valid trace;
3. **OCLI `--help` output** — concrete flags and declared parameter types;
4. **Exact target command name** — constrains the mutation to a real OpenAPI operation.

A simplified evaluation prompt looks like:

```text
=== STATE HISTORY ===
Step 1: ocli auth_register ...
Step 2: ocli projects_post ...
Step 3: ocli milestones_submit ...

=== TARGET ENDPOINT ORIGINAL REQUEST ===
{ ... }

=== AVAILABLE CLI FLAGS ===
--milestoneId string
--status string
...

=== EXACT CLI COMMAND TO USE ===
ocli milestones_id_approve
```

The model then proposes a mutation and, in the evaluation harness, a predicted HTTP status.

Implementation:

```text
p2s/engine/fuzzer.py
p2s/engine/generator.py
p2s/engine/taxonomy.py
p2s/engine/adapters/llm_adapter.py
p2s/engine/adapters/executor.py
```

---

## Security mutation taxonomy

The generation prompt uses a **15-vector taxonomy**:

| # | Vector | Example intent |
|---:|---|---|
| 1 | Null-Byte | inject `\x00` / `%00` into string fields |
| 2 | Type Confusion | replace scalar/object/array/boolean types |
| 3 | Integer Boundary | negative, zero, max-int and extreme values |
| 4 | String Extremes | empty or very large strings |
| 5 | Injection | SQLi and XSS-style payloads |
| 6 | Encoding | double encoding, Unicode / RTL manipulation |
| 7 | Mandatory Omission | omit required parameters |
| 8 | Parameter Conflict | submit mutually inconsistent parameters |
| 9 | IDOR / Path Traversal | substitute identifiers / resource references |
| 10 | Mass Assignment | inject read-only or privileged properties |
| 11 | BOLA / BFLA | challenge ownership / function-level authorization |
| 12 | Business Flow Bypass | skip required business prerequisites |
| 13 | Replay / Idempotency | repeat state-changing actions |
| 14 | Context Desynchronization | mismatch IDs across related resources |
| 15 | Premature Progression | force invalid lifecycle transitions |

Some post-hoc reporting utilities split the combined `Injection` family into separate `SQLi` and `XSS` labels; the generation prompt itself follows the 15-vector formulation above.

---

# 5. Execution is the external signal

P2S is not based on an LLM judging whether its own attack was successful.

The generated command is executed against the target, and the observed response determines the engine label.

```text
model proposes mutation
        ↓
OCLI parses + sends request
        ↓
real backend executes
        ↓
HTTP / CLI outcome observed
        ↓
engine label
```

The research label hierarchy distinguishes:

### `GOLDEN_CRASH`

A candidate label for an observed HTTP `500` / internal server error.

**Interpretation:** an execution-positive server fault. A 500 is **not automatically a security vulnerability**.

### `GOLDEN_RBAC_BYPASS`

A guarded candidate label for a successful 2xx response associated with an authorization/security mutation intent.

**Interpretation:** a candidate that requires semantic verification before being claimed as a security bypass.

### `SILVER`

An executed mutation that reaches a defensive boundary rather than becoming a candidate golden, commonly a `400`, `401`, `403`, `409`, or `422` response.

**Interpretation:** useful negative supervision about where the target rejected the mutation; not proof that every security control is correct.

### CLI syntax failure

The generated command is rejected before a meaningful backend response is observed.

**Interpretation:** not a Golden or Silver example. The error is fed back to the model for self-correction.

---

## Self-correction loop

P2S gives each target step up to **six mutation attempts** in the reported experiments.

```text
attempt
  ↓
CLI error ───────→ return parser error → regenerate
  │
  ├─ Silver ─────→ return boundary status → refine mutation
  │
  └─ Golden ─────→ persist candidate → stop target attempt loop
```

The important point is that the model receives **real execution feedback** between attempts rather than a purely textual critique from another model.

---

# Training corpus

The original AITasker / SourceMarket run captured **48 execution flows and 520 compiled primitive steps**. Base Qwen3.5-9B generated mutations against those flows, with up to six attempts per target step.

The raw execution-grounded corpus was strongly imbalanced:

| Corpus stage | Count |
|---|---:|
| Raw Silver records | 1,917 |
| Silver after deduplication | **1,782** |
| Unique candidate Goldens | **44** |
| Golden block after 10× oversampling | 440 |
| Additional complete Golden copy | 44 |
| **Final SFT corpus** | **2,266** |

The 44 candidate Goldens are not presented as evidence that all modern APIs are similarly hardened. They are an observed property of this source run. Methodologically, the small positive class is useful because the Track-A generalization result is harder to explain as memorization of a large exploit corpus.

Deduplication normalizes content-derived keys and masks values such as emails and timestamps so repeated semantic mutation patterns are collapsed without preserving incidental identifiers.

Implementation:

```text
p2s/dataset/builder.py
```

---

# Fine-tuning Qwen3.5-9B

The final **2,266-record** corpus was used for response-only LoRA adaptation of Qwen3.5-9B with Unsloth.

### Main training configuration

| Setting | Value |
|---|---:|
| Base model | Qwen3.5-9B |
| Training method | LoRA / PEFT |
| LoRA rank `r` | 32 |
| LoRA alpha | 64 |
| LoRA dropout | 0.05 |
| Maximum sequence length | 24,576 |
| Per-device batch size | 1 |
| Gradient accumulation | 4 |
| Effective batch size | 4 |
| Epochs | 6 |
| Peak learning rate | `2e-4` |
| Scheduler | cosine with restarts |
| Optimizer | AdamW 8-bit |
| Weight decay | 0.01 |
| NEFTune noise α | 5.0 |
| Precision | bfloat16 |
| Compute | 1× A100 80 GB |

The text-only task excludes vision layers from adaptation. The training script uses **response-only masking**, so system/user prompt tokens do not contribute to the supervised loss. A real dataloader batch check measured **92.6% of tokens masked** on the verification batch.

### Recorded training run

| Observation | Value |
|---|---:|
| Optimization steps | 3,402 |
| Trainable parameters | 58,195,968 |
| Total parameters | 9,468,009,712 |
| Fraction adapted | **0.61%** |
| Final reported loss | **0.1418** |
| Peak reserved GPU memory | 34.69 GB |
| Runtime | ~8.3 hours |

No measured training record exceeded the configured sequence length.

---

# Published model artifacts

Four Hugging Face repositories are part of the public artifact set:

| Artifact | Purpose | Repository |
|---|---|---|
| LoRA adapter | continued adaptation / PEFT use | [`minhhungg/qwen35-9b-p2s-lora`](https://huggingface.co/minhhungg/qwen35-9b-p2s-lora) |
| Merged 4-bit | Transformers-oriented lower-memory inference | [`minhhungg/qwen35-9b-p2s-merged-4bit`](https://huggingface.co/minhhungg/qwen35-9b-p2s-merged-4bit) |
| Merged 16-bit | canonical merged checkpoint / GGUF source | [`minhhungg/qwen35-9b-p2s-merged-16bit`](https://huggingface.co/minhhungg/qwen35-9b-p2s-merged-16bit) |
| GGUF | llama.cpp deployment (`F16`, `Q8_0`) | [`minhhungg/p2s_gguf`](https://huggingface.co/minhhungg/p2s_gguf) |

The reported P2S evaluation uses the **Q8_0 GGUF**.

### Download the reported GGUF

```bash
pip install -U huggingface_hub

hf download minhhungg/p2s_gguf \
  qwen35-9b-p2s-Q8_0.gguf \
  --local-dir models/p2s
```

### Serve with llama.cpp

The reported fine-tuned evaluation used full GPU offload and the Qwen3.5-9B native context budget:

```bash
llama-server \
  -m models/p2s/qwen35-9b-p2s-Q8_0.gguf \
  --host 0.0.0.0 \
  --port 8081 \
  -ngl 99 \
  -c 262144 \
  --threads 8
```

The server exposes an OpenAI-compatible endpoint used by P2S:

```text
http://localhost:8081/v1/chat/completions
```

The merged 16-bit checkpoint was also converted to an F16 GGUF and then quantized to Q8_0 with `llama.cpp`:

```bash
python convert_hf_to_gguf.py <MERGED_16BIT_DIR> \
  --outfile qwen35-9b-p2s-f16.gguf \
  --outtype f16

./llama-quantize \
  qwen35-9b-p2s-f16.gguf \
  qwen35-9b-p2s-Q8_0.gguf \
  Q8_0
```

See [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md) for the complete model-export and serving procedure.

---

# Track A — independent semantic-security evaluation

Track A tests whether the learned specialization transfers beyond the training application.

### Training environment

```text
AITasker / SourceMarket
NestJS + Prisma + PostgreSQL
companion FastAPI AI service
marketplace / elicitation / bids / milestones / escrow domain
```

### Evaluation environment

```text
SEAL Hackathon backend / HackathonBench
Spring Boot 3 + Java 17 + PostgreSQL
128 REST endpoints
30 persistent tables
JWT / RBAC
21 business flows
hackathon / competition-management domain
```

The target therefore differs from training in language, framework, schema, vocabulary, and domain.

Three model backends share the P2S evaluator:

1. **P2S fine-tuned Qwen3.5-9B Q8_0**;
2. **DeepSeek-V4-Flash-3107**;
3. **untuned Qwen3.5-9B Q8_0**.

A fresh OpenAPI document is fetched before trace compilation and every P2S mutation is executed against reconstructed state.

---

## Semantic adjudication in Track A

Engine candidates pass through an explicit post-hoc validation layer before headline security claims are made.

The validator removes cases including:

- CLI `--help` bleed that never produced a meaningful API request;
- read-only / mass-assignment fields silently ignored by Jackson;
- ordinary authorized 200/201 responses where the claimed security mutation did not actually alter identity or resource ownership;
- other candidate-only cases that do not support the claimed outcome.

Validated records are then deduplicated by endpoint, observed status, and response/error signature.

This separation is intentional:

```text
candidate Golden
      ≠
verified vulnerability
```

Track A distinguishes **verified server faults** from **verified security bypasses** rather than converting every HTTP 500 into a security claim.

Implementation / analysis:

```text
p2s/analytics/verifier.py
p2s/analytics/analyzer.py
p2s/analytics/reclassifier.py
p2s/analytics/m1_analyzer.py
```

---

## Track-A result interpretation

The most important comparison is the architecture-matched control:

```text
Base Qwen3.5-9B          1.4% validated-outcome rate
          │
          │ execution-grounded P2S specialization
          ▼
P2S fine-tuned Qwen3.5   2.9% validated-outcome rate
```

Both models share the same underlying architecture, which makes the comparison more informative than only comparing against a larger external model.

Candidate-level diagnostics also show that the fine-tuned run continued producing execution-positive candidates at primitive-trace positions **14, 22, and 23**, whereas the comparison runs produced none beyond position 13. This is reported as a **search-depth diagnostic**, not proof that a verified vulnerability occurred at depth 23, because the current validator does not retain a record-ID join between every candidate depth and final validated outcome.

---

# Track-A conventional black-box baselines

AutoRestTest, CATS, and Schemathesis were also run against the same evaluation backend under deliberately favorable access conditions: a fresh long-lived Coordinator token, the same live OpenAPI contract, and removal of self-logout / self-deletion operations that could destroy the benchmark identity mid-run.

These tools do **not** use the P2S fine-tuned model; they are independent baselines used to compare native robustness signals with semantically validated stateful findings.

| System | Execution volume | Native failure signal retained | Post-hoc interpretation |
|---|---:|---:|---|
| **P2S FT** | 1,075 records | 24 verified 500s | 31 validated outcomes; 30 unique signatures; 7 verified bypasses |
| AutoRestTest | 806,955 requests / 5 h | 222,802 HTTP 500 | no deep/stateful outcome verified from retained artifacts; all 2,304 persisted error records expose null/empty parameter maps |
| CATS | 45,781 tests | 9,370 dashboard 5xx | no audited disclosure; all 15 IDOR-themed 200 bodies were empty arrays |
| Schemathesis | 10,851 cases | 68 JUnit 5xx | generic catch-all response hides the underlying exception; no deep/stateful outcome verified |

The claim is **not** that these tools found “no bugs.” Their native artifacts contain many robustness failures. The narrower result is that the retained post-hoc evidence did not verify a deep multi-request security outcome comparable to the semantically adjudicated P2S findings.

This avoids three invalid equivalences:

```text
raw HTTP 500             ≠ security vulnerability
operation/path contact   ≠ deep-state reachability
HTTP 200 in IDOR testing ≠ confirmed data disclosure
```

Exact setup and post-hoc commands are documented in [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md).

---

# Track B — SBFT 2026 RESTgym cross-benchmark

Track B evaluates portability across **11 unrelated benchmark services** and multiple state technologies.

Each service receives a **one-hour P2S run**.

| Service | Ops | Persistence / runtime | P2S state adaptation | Strict 5xx signatures |
|---|---:|---|---|---:|
| `blog` | 52 | Spring / MySQL | SQL reseed in container | **31** |
| `erc20` | 13 | Spring / Web3j / Ganache | redeploy fresh contract; proxy rewrites dummy address | **19** |
| `features-service` | 18 | Spring / H2 | enable service; restart resets H2 | **83** |
| `flight-search` | 40 | Spring / MongoDB | ADMIN test identity + MongoDB reseed | **0** |
| `gestao-hospital` | 20 | Spring / MongoDB | session auth + DB drop/reseed | **1** |
| `kafka-rest-proxy` | 50 | Confluent Kafka REST | delete/recreate target topic | **7** |
| `market` | 13 | Spring / H2 | enable service + restart | **29** |
| `notebook-manager` | 5 | Spring / MySQL | schema/data SQL re-import | **25** |
| `person-controller` | 12 | Spring / embedded Mongo | restart resets state | **58** |
| `pet-clinic` | 35 | Spring / H2 | `/petclinic` context + Basic `admin:admin` | **60** |
| `project-tracking-system` | 59 | Spring / H2 / Flyway | restart replays Flyway + seeds | **8** |
| **Total / mean** | **317** | — | — | **321 / 29.18 API** |

The service-specific reset mechanisms are important: they demonstrate that P2S is not hard-coded to the PostgreSQL environment used for training.

In v1.2, the generic execution shape is framework-native and the service-specific differences live in TOML:

```bash
export RESTGYM_ROOT=/path/to/restgym

# Example: one Track-B service
p2s doctor  -c configs/research/track_b/pet-clinic.toml --workdir runs/track-b/pet-clinic
p2s prepare -c configs/research/track_b/pet-clinic.toml --workdir runs/track-b/pet-clinic
p2s record  -c configs/research/track_b/pet-clinic.toml --workdir runs/track-b/pet-clinic
p2s compile -c configs/research/track_b/pet-clinic.toml --workdir runs/track-b/pet-clinic
p2s fuzz    -c configs/research/track_b/pet-clinic.toml --workdir runs/track-b/pet-clinic --time-budget 3600 --cyclic
p2s coverage -c configs/research/track_b/pet-clinic.toml --workdir runs/track-b/pet-clinic
p2s fd --golden-file runs/track-b/pet-clinic/petclinic_p2s_golden_dataset.jsonl \
  --dedup-out runs/track-b/pet-clinic/petclinic_strict_5xx.jsonl
```

RESTgym's own mitmproxy remains semantically active on port `9090` where the benchmark requires authentication or request rewriting; P2S does not replace it. The complete per-service patches, launch rules, authentication behavior, reset commands, and coverage steps are documented in [`docs/TRACK_B_WITH_P2S_FRAMEWORK.md`](docs/TRACK_B_WITH_P2S_FRAMEWORK.md).

---

## Track-B measurement boundary

The REST League's Fault Detection metric is intentionally **5xx-only**. P2S candidate goldens can also represent successful 2xx security-intent candidates.

Therefore the Track-B comparison first filters to `status >= 500` and only then deduplicates.

```text
all P2S candidate goldens
        │
        ├── 5xx ──→ status-aligned FD proxy
        │
        └── 2xx ──→ excluded from SBFT FD
                    retained separately as candidates
```

The reported 321 total is consequently a **status-aligned P2S-native proxy**, not an official Restats FD measurement. P2S uses its own fault-signature key rather than Restats's exact equivalence implementation.

Likewise:

- P2S has **one repetition per service**, while official REST League sessions use repeated runs;
- P2S operation coverage is trace-derived rather than retained native Restats `OC`;
- no P2S metric-time trajectory was retained, so **no P2S Roadrunner / AUC efficiency score is claimed**;
- final JaCoCo snapshots may be non-cumulative on services whose state adapter restarts the target JVM.

These limitations are part of the published interpretation, not hidden implementation details.

---

## Structural coverage vs semantic security

Final Track-B JaCoCo snapshots average approximately:

| Metric | P2S mean |
|---|---:|
| Branch coverage | 14.46% |
| Line coverage | 27.37% |
| Method coverage | 29.07% |
| Trace-derived operations / API | 25.55 |

The research does **not** interpret low source coverage as proof that coverage is unimportant. Instead, Track A and Track B together demonstrate that coverage, crash diversity, and semantic security answer different questions.

Track B retained **6,485 API-response records** across the eleven one-hour sessions (589.5/API-hour). The published AutoRestTest CSVs average roughly 143,332 interactions/API-hour. Because these counters are not proven identical, the roughly 243× difference is reported only as an **order-of-magnitude traffic contrast**, not a like-for-like compute-efficiency claim. P2S also incurs LLM inference and state-reset cost.

---

# Metrics used by the P2S evaluator

### M1 — Syntax Pass Rate

Did the generated command pass the CLI/parser layer and reach the target API?

```text
M1 = API-reaching commands / scoreable fired commands
```

This separates model/CLI formatting failures from actual backend behavior.

### M2 — Boundary Prediction

The evaluation harness asks the model to predict the HTTP response before execution, then compares `predicted_status` with `actual_status`.

Two views are useful:

- **exact status match**, e.g. predicted 403 and observed 403;
- **HTTP class match**, e.g. predicted 400 and observed 422.

M2 measures outcome calibration. It does **not** verify that a candidate Golden is a vulnerability.

### Candidate-positive / Golden rate

How frequently does the engine produce an execution-positive candidate rather than a defended Silver boundary?

### Validated-outcome rate

Track A uses the stronger post-hoc denominator:

```text
validated outcomes / executed records
```

This is the headline semantic comparison between P2S, DeepSeek, and base Qwen.

---

---

# Installing P2S — what the commands actually do

There are two normal installation modes. **Choose one; you do not need both.**

## Option A — install the wheel

Use this when you want to consume P2S as a package without editing its source.

### 1. Open a terminal in the directory containing the wheel

In a release bundle it is normally under `dist/`:

```text
dist/p2s_framework-1.2.0-py3-none-any.whl
```

### 2. Create an isolated Python environment

```bash
python -m venv .venv
```

Activate it with the command appropriate for your shell:

```bash
# Windows Git Bash
source .venv/Scripts/activate

# Windows PowerShell
# .venv\Scripts\Activate.ps1

# Windows cmd.exe
# .venv\Scripts\activate.bat

# Linux / macOS
# source .venv/bin/activate
```

### 3. Install the wheel

From the release root:

```bash
python -m pip install --upgrade pip
python -m pip install ./dist/p2s_framework-1.2.0-py3-none-any.whl
```

If the wheel is in the current directory instead:

```bash
python -m pip install ./p2s_framework-1.2.0-py3-none-any.whl
```

`pip` automatically installs the Python runtime dependencies declared in `pyproject.toml` (`httpx`, `openai`, `psycopg2-binary`, `PyYAML`, and `tomli` on Python < 3.11).

### 4. Verify the installation

```bash
python -c "import p2s; print(p2s.__version__)"
p2s --help
python -m p2s --help
```

Expected version:

```text
1.2.0
```

## Option B — install from source in editable mode

Use this when you cloned the GitHub repository and want changes to `p2s/` to take effect immediately.

```bash
git clone <THIS_REPOSITORY_URL>
cd <P2S_REPOSITORY_ROOT>    # the directory containing pyproject.toml

python -m venv .venv
source .venv/Scripts/activate       # Git Bash / Windows
# source .venv/bin/activate         # Linux/macOS

python -m pip install --upgrade pip
python -m pip install -e .
```

For contributors/tests/build tooling:

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
```

For the optional in-process Transformers backend:

```bash
python -m pip install -e ".[transformers]"
```

Editable install means Python imports the package from your working tree rather than copying a fixed snapshot into `site-packages`.

## What else is required after installation?

For **`import p2s` / SDK inspection**, nothing beyond the Python installation is required.

For **actual P2S execution**, install/configure the pieces used by your chosen target:

| Need | Why |
|---|---|
| Target API | P2S executes mutations against a live, authorized test target |
| OpenAPI / Swagger document | grounds captured HTTP traffic into executable operations |
| Node.js + OCLI | default research executor used to generate/execute OpenAPI-grounded CLI commands |
| LLM endpoint | produces state-conditioned mutations; OpenAI-compatible endpoints are supported |
| State-reset tooling | PostgreSQL / Docker / MongoDB / file / arbitrary command depending on target |
| Target research repo | only for reproducing AITasker, SEAL Track A, or RESTgym Track B |

Install OCLI separately because it is a Node.js tool rather than a Python dependency:

```bash
npm install -g openapi-to-cli
ocli --help
```

Then read [`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md), which walks through the first config, `doctor`, target preparation, trace recording, compilation, model configuration, fuzzing, and outputs.

---

# First-time usage — the shortest useful workflow

P2S is configuration-driven. The same Python implementation is reused; the TOML file describes target-specific URLs, patches, authentication, state resets, trace handling, and model endpoint.

```bash
# 0. activate the virtual environment first
source .venv/Scripts/activate

# 1. inspect whether the target/config prerequisites exist
p2s doctor -c path/to/target.toml --workdir runs/my-target

# 2. apply configured safe/idempotent target patches and launch/readiness steps
p2s prepare -c path/to/target.toml --workdir runs/my-target

# 3. execute/freeze a representative valid workflow
p2s record -c path/to/target.toml --workdir runs/my-target

# 4. compile HTTP trace → OpenAPI-grounded executable trace + OCLI catalog
p2s compile -c path/to/target.toml --workdir runs/my-target

# 5. run state-conditioned mutation/evaluation
p2s fuzz -c path/to/target.toml --workdir runs/my-target

# 6. collect target coverage when configured
p2s coverage -c path/to/target.toml --workdir runs/my-target

# 7. cleanup launched research resources when configured
p2s cleanup -c path/to/target.toml --workdir runs/my-target
```

You do **not** need to run every command separately when the profile's `prepare` stage already performs patch/fetch/auth/launch work; the explicit commands are exposed so researchers can inspect and debug each stage independently.

### What files should appear?

A typical run directory evolves roughly as follows:

```text
runs/my-target/
├── primitive_traces.jsonl
├── compiled_traces.jsonl
├── ocli_catalog.json
├── *_golden_dataset.jsonl
├── *_silver_dataset.jsonl
├── *_processed_flows.txt
├── *_execution_log.txt
└── *_run_metadata.json
```

Golden files are **candidate execution-positive findings**. They are not automatically verified vulnerabilities. Track A uses an additional semantic validation/deduplication step; Track B's benchmark FD comparison filters to 5xx before deduplication.

---

# Python SDK — the same lifecycle without shell commands

```python
from p2s import P2S

sdk = P2S.from_toml(
    "configs/research/track_a_seal_p2s.toml",
    workdir="runs/track-a/p2s",
)

issues = sdk.doctor()
if issues:
    raise RuntimeError("\n".join(issues))

sdk.prepare()
sdk.record()
compiled, catalog = sdk.compile()
fuzzer = sdk.fuzz()
print(fuzzer.metrics)
sdk.coverage()
sdk.cleanup()
```

The high-level facade intentionally mirrors the CLI. See [`SDK_GUIDE.md`](SDK_GUIDE.md) for the method-by-method guide, custom-target walkthrough, adapters, generated artifacts, and troubleshooting.

---

# CLI reference

```text
p2s doctor             preflight configuration/environment
p2s patch              apply configured idempotent target patches
p2s fetch-openapi      fetch/sanitize configured OpenAPI
p2s auth               acquire controlled test credential
p2s prepare            patch + prepare/launch/readiness + OpenAPI/auth
p2s proxy              run the P2S trace-capture proxy
p2s record             run workload/freeze baseline primitive trace
p2s compile            primitive trace → executable OpenAPI-grounded trace
p2s fuzz               state-conditioned mutation + live execution
p2s generate-data      execution-grounded self-play corpus generation
p2s prepare-dataset    deduplicate/stratify final SFT dataset
p2s coverage           run target-specific coverage collection
p2s cleanup            run configured cleanup
p2s analyze            summarize Golden/Silver run artifacts
p2s reclassify         attack-vector post-hoc classification
p2s m1                 syntax/execution-pass analysis
p2s verify             Track-A candidate verification/dedup pipeline
p2s fd                 strict 5xx-before-dedup Track-B fault proxy
```

`python -m p2s ...` is equivalent to the `p2s ...` console command.

---

# Configuration: where target-specific behavior lives

A minimal conceptual profile looks like this:

```toml
[target]
name = "my_api"
base_url = "http://localhost:8080/api"
openapi_spec = "openapi.json"
state_adapter = "docker"
executor_adapter = "ocli"
golden_out = "my_api_golden_dataset.jsonl"
silver_out = "my_api_silver_dataset.jsonl"

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

Research profiles add `[research]`, `[openapi_setup]`, `[auth]`, `[[patches]]`, and target-specific state sections. The authoritative schema is [`docs/CONFIGURATION_REFERENCE.md`](docs/CONFIGURATION_REFERENCE.md).

---

# Reproducing the research with v1.2

The public reproduction path deliberately uses **one P2S package** rather than the slightly different P2S helper files used during development.

```text
AITasker workload/state facts ─┐
SEAL workload/state facts ─────┼──> configs/research/*.toml ──> shared p2s package
RESTgym service facts ─────────┘
```

Start with [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md). It branches into:

- [`docs/TRACK_A_WITH_P2S_FRAMEWORK.md`](docs/TRACK_A_WITH_P2S_FRAMEWORK.md) — P2S / Base Qwen / DeepSeek on SEAL plus AutoRestTest, CATS, Schemathesis;
- [`docs/TRACK_B_WITH_P2S_FRAMEWORK.md`](docs/TRACK_B_WITH_P2S_FRAMEWORK.md) — the exact service patches/auth/proxy/reset requirements for all 11 RESTgym services;
- [`docs/MODEL_AND_TRAINING.md`](docs/MODEL_AND_TRAINING.md) — corpus preparation, Qwen3.5-9B LoRA training, exports, and llama.cpp serving.

The original one-off scripts and historical instructions remain under [`original_reporducibility_docs/`](original_reporducibility_docs/README.md) so reviewers can audit how the normalized framework maps back to the experiment implementation.

**Resolved baseline configuration:** the completed original AutoRestTest Track-A run used **DeepSeek-V4-Flash-3107**. Older AutoRestTest local-base-Qwen material is historical only.

---

# Repository map

```text
p2s/
├── proxy/            trace capture
├── compiler/         OpenAPI/OCLI grounding
├── engine/           mutation, execution, state adapters, LLM adapters
├── dataset/          self-play corpus construction
├── analytics/        verification, reclassification, metrics, strict 5xx FD
└── research/         patch/launch/auth/OpenAPI/coverage lifecycle orchestration

configs/research/     framework-native profiles for the full study
docs/                 canonical v1.2 framework-native documentation
original_reporducibility_docs/
                      frozen historical procedures/helpers for audit fidelity
tests/                framework and research-regression tests
SDK_GUIDE.md          Python API / first-user guide
pyproject.toml        package metadata and dependencies
```

---

# What are `build/` and `dist/`?

They are **packaging outputs**, not core P2S source code.

```text
build/      temporary setuptools build workspace
            generated while building the package; safe to delete/regenerate

dist/       final distributable artifacts
            e.g. p2s_framework-1.2.0-py3-none-any.whl and optionally .tar.gz

*.egg-info/ generated package metadata during editable/source builds
```

For ordinary development you only need the source tree plus a virtual environment. A clean rebuild is:

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m build
```

For a GitHub project, a common practice is to keep `build/`, `dist/`, and `*.egg-info/` out of normal source commits and attach the wheel to a GitHub Release. This release bundle keeps a `dist/` wheel as a convenience artifact, but the directory can always be regenerated from `pyproject.toml` + source.

See [`docs/BUILD_AND_RELEASE.md`](docs/BUILD_AND_RELEASE.md).

---

# What P2S does *not* claim

The repository intentionally keeps several distinctions explicit.

### A 500 response is not automatically a vulnerability

It is a server fault. Security claims require additional evidence.

### A candidate 2xx bypass is not automatically verified

Track A performs post-hoc semantic adjudication. Track-B 2xx candidates remain candidates only.

### Low source coverage does not prove greater semantic depth

Coverage and semantic security are different constructs. The paper reports their observed divergence without claiming a universal inverse relationship.

### Low request volume does not prove lower compute cost

P2S trades network volume for LLM inference and state restoration. A proper compute comparison would need wall-clock component timing, token counts, energy, and equivalent instrumentation.

### Track B is not an official SBFT submission

The P2S runs use one repetition per service, a P2S-native status-compatible FD proxy, trace-derived OC, and no native metric-time series for official AUC scoring.

### The current experiment is not a full ablation study

The research does not independently attribute transfer gains to any one of oversampling, LoRA target modules, dropout, NEFTune, retry behavior, or scheduler choice.

---

# Threats to validity

The main threats retained from the research are:

- **single stochastic runs in Track A** — results demonstrate observed transfer, not a distribution over repeated seeds;
- **candidate vs validated outcome separation** — candidate-level depth/vector analyses should not be conflated with final verified security outcomes;
- **serving-wrapper difference** — the fine-tuned Q8_0 model used bare `llama-server`, while the base Qwen control was served through LM Studio; both used the same context budget, but runtime differences remain a possible confound;
- **state-reset assumptions** — the historical dirty-flag optimization does not transactionally prove that every 4xx response is side-effect free;
- **Track-B single repetition** — not directly comparable to ten-run competition means for statistical claims;
- **P2S-native FD deduplication** — status-compatible with 5xx-only REST League FD but not an exact Restats implementation;
- **trace-derived Track-B OC** — not retained as a native Restats measurement;
- **no Track-B metric-time trajectory** — official efficiency / Roadrunner AUC cannot be reconstructed and is therefore not reported;
- **JaCoCo restart effects** — final coverage snapshots may be non-cumulative when state reset restarts the target JVM.

These are documented because reproducibility means reproducing both the results **and the boundaries of what those results support**.

---

# Documentation

| Document | Purpose |
|---|---|
| [`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md) | first installation and first target, step by step |
| [`SDK_GUIDE.md`](SDK_GUIDE.md) | detailed Python SDK + CLI usage |
| [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md) | canonical full research reproduction |
| [`docs/TRACK_A_WITH_P2S_FRAMEWORK.md`](docs/TRACK_A_WITH_P2S_FRAMEWORK.md) | Track A setup, model controls, external baselines |
| [`docs/TRACK_B_WITH_P2S_FRAMEWORK.md`](docs/TRACK_B_WITH_P2S_FRAMEWORK.md) | all 11 RESTgym service adaptations |
| [`docs/MODEL_AND_TRAINING.md`](docs/MODEL_AND_TRAINING.md) | training/export/serving |
| [`docs/CONFIGURATION_REFERENCE.md`](docs/CONFIGURATION_REFERENCE.md) | TOML schema |
| [`docs/HISTORICAL_TO_FRAMEWORK_MAPPING.md`](docs/HISTORICAL_TO_FRAMEWORK_MAPPING.md) | old helper → v1.2 mapping |
| [`docs/BUILD_AND_RELEASE.md`](docs/BUILD_AND_RELEASE.md) | wheel/source build artifacts and releases |
| [`original_reporducibility_docs/`](original_reporducibility_docs/README.md) | frozen historical parity archive |

---

# Public research status

The manuscript is still in anonymous review, so the paper PDF and identifying submission material are intentionally not published here. The README therefore acts as the public high-level research record: it documents the problem, architecture, data generation, training setup, evaluation design, headline results, metric boundaries, limitations, public models, and reproduction entry points without requiring access to the submission PDF.

---

# Responsible use

P2S is intended for security testing of systems you own, local research benchmarks, disposable test deployments, and systems for which you have explicit authorization. The supplied research profiles are designed around controlled local/Dockerized targets. Do not point the framework at third-party production services without permission.

---

# Release

**P2S Framework v1.2.0** is the framework-native research-reproduction release.

Its main architectural change is that AITasker, SEAL Track A, and RESTgym Track B now share the same public P2S implementation; target-specific patches, authentication, state restoration, workload handling, and lifecycle steps are represented declaratively in research TOML profiles. Historical one-off implementations are retained separately for audit fidelity rather than used as the default user path.
