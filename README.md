# P2S — Primitive-to-Semantics

> **Deep-State REST API Security Testing Beyond Code Coverage**

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Release](https://img.shields.io/badge/release-v1.1.0-4c1)
![Research](https://img.shields.io/badge/artifact-reproducible-purple)
![OpenAPI](https://img.shields.io/badge/interface-OpenAPI%20%2B%20OCLI-orange)

**P2S (Primitive-to-Semantics)** is an execution-grounded framework for stateful REST API security testing. It captures successful multi-step API traces, grounds them against an OpenAPI specification, converts them into executable OCLI primitives, reconstructs the prerequisite business state before each target request, and asks an LLM to generate fault-seeking mutations. Those mutations are executed against a resettable backend, so the **live system response—not another model—is the external execution signal** used for self-play data generation and evaluation.

The project focuses on security behaviors whose meaning depends on **identity, ownership, lifecycle state, prior requests, and business-flow history**. A request can be syntactically valid and reach the same code path as a legitimate request while still violating a security invariant—for example, modifying another user's resource, progressing an object before prerequisites are met, or exercising a privileged transition in the wrong state.

This repository contains the reusable **P2S Framework / Python SDK** extracted from the research implementation.

> **Manuscript ↔ public artifact naming.** The anonymized manuscript refers to the training system as **SourceMarket** and the independent Track-A system as **HackathonBench**. In the public research artifacts these correspond to **AITasker** and the **SEAL Hackathon backend**, respectively.

---

## TL;DR — what was demonstrated

P2S was trained from execution-grounded self-play on one application and evaluated on unrelated systems and technology stacks.

### Track A — independent deep-state backend

The fine-tuned P2S Qwen3.5-9B specialist was evaluated zero-shot on an independently developed **128-endpoint Spring Boot / PostgreSQL backend with 21 stateful business flows**. The same P2S harness was used for the fine-tuned model, DeepSeek-V4-Flash, and an architecture-matched untuned Qwen3.5-9B control.

| Metric | **P2S Fine-Tuned** | DeepSeek-V4-Flash | Base Qwen3.5-9B |
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

In this single-run evaluation, P2S produced approximately **2.02× the validated-outcome rate of the untuned architecture-matched control** and **1.21× that of DeepSeek-V4-Flash**.

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
2. **DeepSeek-V4-Flash**;
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

The generic experimental shape is:

```bash
python3 trace_compiler.py \
  --swagger <service-spec> \
  --input <primitive_traces.jsonl> \
  --output <compiled_traces.jsonl> \
  --catalog <ocli_catalog.json>

python3 eval_student_p2s_engine.py \
  --target-port 9090 \
  --traces <compiled_traces.jsonl> \
  --catalog <ocli_catalog.json> \
  --output-prefix <service>_p2s \
  --time-budget 3600

python dedup_p2s_goldens.py \
  <service>_p2s_golden_dataset.jsonl

# JaCoCo dump -> results/<service>/code-coverage/coverage.csv
```

The complete service-by-service commands and patches are retained in [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md).

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

# Install the SDK

## From the release wheel

```bash
pip install p2s_framework-1.1.0-py3-none-any.whl
```

## Editable development install

```bash
git clone <THIS_REPOSITORY_URL>
cd p2s-framework
pip install -e .
```

Verify the installation:

```bash
p2s --help
python -m p2s --help
```

Python **3.10+** is supported by the packaged SDK.

---

# Python SDK quick start

```python
from p2s import P2S

sdk = P2S.from_toml(
    "configs/target.toml",
    workdir="runs/target",
)

# 1. primitive traces -> OpenAPI-grounded executable traces
compiled, catalog = sdk.compile()

# 2. execution-verified evaluation
fuzzer = sdk.fuzz()

# 3. execution-grounded self-play training data
sdk.generate_data()

# 4. deduplicate / stratify training corpus
sdk.prepare_dataset()
```

The facade intentionally stays thin: SDK calls and the CLI reuse the same underlying framework implementation.

---

# CLI

```bash
# Capture traffic
p2s proxy --config configs/target.toml

# Compile primitive traces
p2s compile --config configs/target.toml

# Evaluate a model
p2s fuzz --config configs/target.toml

# Generate execution-grounded SFT data
p2s generate-data --config configs/target.toml

# Build final deduplicated / stratified corpus
p2s prepare-dataset --config configs/target.toml
```

Post-hoc tooling:

```bash
p2s verify
p2s analyze
p2s reclassify
p2s m1
```

Available command families in v1.1.0:

```text
proxy
compile
fuzz
generate-data
prepare-dataset
analyze
reclassify
m1
verify
```

---

# Example configuration

```toml
[target]
name = "seal_hackathon"
base_url = "http://localhost:8080/api"
openapi_spec = "seal_openapi.json"
state_adapter = "postgres"
executor_adapter = "ocli"
golden_out = "llamacpp_golden_dataset.jsonl"
silver_out = "llamacpp_silver_dataset.jsonl"
checkpoint_file = "processed_flows.txt"

[postgres]
active_db = "seal_hackathon"
template_db = "seal_hackathon_snap"
admin_url = "postgresql://postgres:postgres@localhost:5432/postgres"
seed_command = "psql -U postgres -d seal_hackathon -f seal_hackathon_full.sql"
setup_script = "hooks/seal_setup_hook.py"

[llm]
backend = "openai_compat"
base_url = "http://localhost:8081/v1"
model = "qwen35-9b-p2s"
api_key = "no-key"
max_attempts = 6

[proxy]
listen_port = 8090
target_host = "http://localhost:8080"
flow_strategy = "header"
output_file = "primitive_traces.jsonl"
```

The SDK supports OpenAI-compatible model servers such as `llama.cpp` and LM Studio, plus local Transformers-based inference.

---

# Repository map — where to inspect the implementation

A professor or reviewer can validate the implementation from the following files without reading the full technical reference first.

```text
p2s/
├── __init__.py
├── __main__.py
├── sdk.py                         # public P2S / P2SClient facade
├── cli.py                         # `p2s ...` command dispatcher
├── config.py                      # TOML configuration loading
│
├── proxy/
│   └── core_proxy.py              # transparent trace capture
│
├── compiler/
│   └── compiler.py                # OpenAPI route matching + OCLI compilation
│
├── engine/
│   ├── taxonomy.py                # mutation taxonomy + prompt rules
│   ├── generator.py               # self-play / training-data generation
│   ├── fuzzer.py                  # execution-verified evaluator
│   └── adapters/
│       ├── state_adapter.py       # target state reset / snapshot abstraction
│       ├── executor.py            # OCLI / HTTP execution abstraction
│       └── llm_adapter.py         # local / OpenAI-compatible inference
│
├── dataset/
│   └── builder.py                 # deduplication + final SFT corpus
│
└── analytics/
    ├── verifier.py                # Golden verification / FP filtering
    ├── analyzer.py                # cross-run metrics / reporting
    ├── reclassifier.py            # attack-vector post-hoc classification
    └── m1_analyzer.py             # CLI syntax-pass analysis
```

Other important files:

```text
configs/aitasker.toml
configs/seal_hackathon.toml
hooks/seal_setup_hook.py
SDK_GUIDE.md
docs/P2S_FRAMEWORK_REFERENCE.md
docs/REPRODUCIBILITY.md
tests/test_sdk_smoke.py
pyproject.toml
```

---

# Paper → artifact validation map

This table is intended specifically to make project assessment easier.

| Paper / research claim | Where to validate |
|---|---|
| Transparent HTTP trace capture | `p2s/proxy/core_proxy.py` |
| OpenAPI grounding and executable CLI representation | `p2s/compiler/compiler.py` |
| 15-vector mutation taxonomy | `p2s/engine/taxonomy.py` |
| State replay / isolated mutation execution | `p2s/engine/fuzzer.py`, `p2s/engine/adapters/state_adapter.py` |
| Self-play training-data generation | `p2s/engine/generator.py` |
| Golden / Silver dataset preparation | `p2s/dataset/builder.py` |
| M1 / post-hoc evaluation | `p2s/analytics/` |
| AITasker training-corpus reproduction | `docs/REPRODUCIBILITY.md` → AITasker section |
| P2S Qwen fine-tuning | AITasker research artifact + training notebook |
| LoRA / merged / GGUF checkpoints | Hugging Face repositories listed above |
| Track A P2S / base / DeepSeek experiment | `docs/REPRODUCIBILITY.md` → SEAL Track A |
| AutoRestTest baseline | `docs/REPRODUCIBILITY.md` → AutoRestTest Track A |
| CATS / Schemathesis baselines | `docs/REPRODUCIBILITY.md` → CATS & Schemathesis |
| Track B 11-service benchmark | `docs/REPRODUCIBILITY.md` → RESTgym Track B |
| Per-service coverage artifacts | RESTgym research artifact `results/<service>/code-coverage/coverage.csv` |

---

# Full research artifact ecosystem

The SDK repository is deliberately kept separate from large datasets, benchmark repositories, and model checkpoints.

```text
P2S research project
│
├── 1. p2s-framework
│      reusable Python SDK / CLI
│      ← this repository
│
├── 2. AITasker training artifact
│      proxy / compiler / P2S generation workflow
│      primitive + compiled traces
│      Golden + Silver JSONL
│      final 2,266-record SFT JSONL
│      training notebook
│
├── 3. P2S model artifacts
│      LoRA
│      merged 4-bit
│      merged 16-bit
│      GGUF F16 + Q8_0
│
├── 4. Track A — SEAL / HackathonBench artifact
│      P2S fine-tuned run
│      base-Qwen run
│      DeepSeek run
│      verified / reclassified JSONL
│      AutoRestTest artifacts
│      CATS report
│      Schemathesis artifacts
│
├── 5. Track B — RESTgym artifact
│      11 services / 317 operations
│      primitive + compiled traces
│      Golden / Silver JSONL per service
│      results/<service>/code-coverage/coverage.csv
│
└── 6. AutoRestTest-SEAL artifact
       data/seal_openapi/*.json
       generated graph / Q-table / error artifacts
```

The separation has two benefits:

1. `pip install` remains a lightweight reusable framework rather than downloading gigabytes of experiment data;
2. research outputs remain auditable in the repositories where they were actually produced.

---

# Reproduce the research

The detailed reproduction guide is:

> **[`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md)**

It contains exact setup, files, commands, target-specific patches, reset mechanisms, and output locations for five complete research operations:

### 1. AITasker — training-data generation

```text
git clone AITasker
switch feat/hung/SWT-Main
      ↓
run FastAPI + NestJS
      ↓
P2S proxy
      ↓
20 mainflow scripts
      ↓
primitive traces
      ↓
OpenAPI-grounded compilation
      ↓
base Qwen3.5-9B self-play
      ↓
Golden / Silver
      ↓
dedup + stratification
      ↓
final_training_dataset.jsonl
      ↓
LoRA fine-tuning
```

### 2. Track A — P2S / base Qwen / DeepSeek on SEAL

Includes:

- PostgreSQL reset and seed;
- Spring Boot launch;
- header-tagged trace capture;
- 21 business flows;
- trace compilation;
- P2S evaluator configuration;
- llama.cpp P2S serving;
- base-Qwen and DeepSeek comparison runs;
- Golden validation;
- deduplication;
- vector reclassification;
- final analytics.

### 3. AutoRestTest Track A

Includes the exact AutoRestTest repository setup, protected OpenAPI document, Coordinator token handling, five-hour run, socket-throttling fix, `data/seal_openapi/` artifacts, and post-hoc parsing.

### 4. CATS + Schemathesis Track A

Includes the same stabilized SEAL contract / authentication environment and exact commands used to produce `cats_report/`, JUnit, VCR, and `.schemathesis/` artifacts.

### 5. RESTgym Track B

Includes all eleven services individually:

```text
blog
erc20
features-service
flight-search
gestao-hospital
kafka-rest-proxy
market
notebook-manager
person-controller
pet-clinic
project-tracking-system
```

with each service's Docker build, trace recording script, OpenAPI file, compiler command, one-hour P2S invocation, reset strategy, post-processing, and JaCoCo extraction.

---

# Framework path vs historical experiment path

The research evolved before the reusable SDK was extracted, so the raw experimental repositories contain several task-specific versions of:

```text
proxy.py
trace_compiler.py
eval_student_p2s_engine.py
```

The public framework normalizes those implementations into reusable modules.

```text
historical proxy variants
        ↓
p2s.proxy

historical trace compilers
        ↓
p2s.compiler

AITasker self-play engine
        ↓
p2s.engine.generator

SEAL / RESTgym evaluation engines
        ↓
p2s.engine.fuzzer
        + target state adapters
```

For **paper-exact reproduction**, follow the historical-parity commands documented in `docs/REPRODUCIBILITY.md`.

For **new systems and normal SDK use**, use the generalized `p2s` package.

This distinction is explicit so the repository does not falsely imply that every historical benchmark-specific workaround existed in exactly the same abstraction during the original experiment.

---

# Extending P2S to a new API

At a high level, integrating another OpenAPI-described system requires four things:

```text
1. representative successful flows
2. an OpenAPI document
3. an execution adapter / target URL
4. a repeatable state-reset strategy
```

Then:

```bash
p2s proxy --config configs/new_target.toml
# exercise representative flows through the proxy

p2s compile --config configs/new_target.toml

p2s fuzz --config configs/new_target.toml
```

For self-play data generation instead of evaluation:

```bash
p2s generate-data --config configs/new_target.toml
p2s prepare-dataset --config configs/new_target.toml
```

P2S does **not** automatically discover every meaningful business flow. Representative traces remain an important source of semantic reachability. The proxy simply makes those flows reusable once they have been exercised.

---

# Verification checklist for reviewers / instructors

A quick repository audit can be performed in roughly this order:

### A. Package integrity

```bash
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows PowerShell

pip install -e .
p2s --help
pytest -q
```

### B. Inspect architectural modules

```text
p2s/proxy/core_proxy.py
p2s/compiler/compiler.py
p2s/engine/fuzzer.py
p2s/engine/generator.py
p2s/engine/taxonomy.py
p2s/engine/adapters/
p2s/dataset/builder.py
p2s/analytics/
```

### C. Inspect research configuration

```text
configs/aitasker.toml
configs/seal_hackathon.toml
hooks/seal_setup_hook.py
```

### D. Inspect reproduction protocol

```text
docs/REPRODUCIBILITY.md
```

### E. Inspect model artifacts

Use the four Hugging Face repositories in the **Published model artifacts** section.

### F. Cross-check paper results

Track-A and Track-B headline values are reproduced in the tables near the top of this README, with their limitations stated alongside them.

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
| [`README.md`](README.md) | research overview, results, architecture, quick validation |
| [`SDK_GUIDE.md`](SDK_GUIDE.md) | Python SDK usage and integration |
| [`docs/P2S_FRAMEWORK_REFERENCE.md`](docs/P2S_FRAMEWORK_REFERENCE.md) | full implementation reference |
| [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md) | complete paper-level experimental reproduction |
| [`CHANGELOG.md`](CHANGELOG.md) | release history |

---

# Research paper

This repository is the software artifact for:

> **P2S: Primitive-to-Semantics for Deep-State REST API Security Testing Beyond Code Coverage**

The manuscript's central empirical argument is not that code coverage or conventional REST testing is “wrong.” It is that modern API-security evaluation benefits from an additional semantic axis for outcomes that depend on identity, ownership, lifecycle state, and prior requests.

A formal citation / DOI can be added here once the paper's public bibliographic record is available.

---

# Responsible use

P2S generates adversarial REST API mutations. Use it only against:

- systems you own;
- systems for which you have explicit authorization to test; or
- isolated benchmark / research environments.

The reported experiments were performed against local or Dockerized systems under study control with resettable state. Do not point the framework at third-party production services without authorization.

---

# Release

**v1.1.0 — first public P2S Python SDK release**

The v1.1.0 release packages the reusable framework independently from the large research datasets, benchmark repositories, and model checkpoints while preserving exact experimental procedures in `docs/REPRODUCIBILITY.md`.
