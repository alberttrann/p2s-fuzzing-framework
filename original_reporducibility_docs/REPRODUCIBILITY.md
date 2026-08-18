# P2S Research Reproducibility & Expansion Guide

**Companion documentation for P2S Framework v1.1.0**  
**Research project:** *P2S: Primitive-to-Semantics Training for Execution-Verified API Security Fuzzing via Self-Play and Specialist LLM Adaptation*

This document consolidates the experiment procedures that were originally spread across several development notes and target-specific scripts. Its purpose is to make the complete research pipeline reproducible without pretending that every historical experiment used one byte-identical proxy, compiler, or runner.

P2S was developed iteratively. AITasker training-data generation, SEAL Track A, and the eleven RESTgym Track B services each exposed target-specific requirements: different authentication, context paths, database reset mechanisms, proxy flow-boundary rules, and execution budgets. **P2S Framework v1.1.0 is the normalized reusable layer extracted from those experiments.** Target-specific setup remains configuration, hooks, or research-harness code rather than being baked into the core engine.

The repository root also includes `p2s_colab_train.ipynb` as a **training-reproduction example**. It is intentionally outside the `p2s/` package: the SDK produces `final_training_dataset.jsonl`; the notebook is one downstream consumer that reproduces the paper's Qwen3.5-9B specialization on Colab/A100. Installing the wheel does not install or require the notebook's Unsloth/TRL stack.

> **Authorized testing only.** All commands below assume an isolated local research environment, disposable state, and systems that you own or have explicit permission to test.

---

## 1. What This Guide Reproduces

The research is split into five operational packages:

| Operation | Target / tool | Role in the paper | Uses P2S fine-tuned model? |
|---|---|---|---|
| **1** | AITasker | Capture stateful traces, generate Golden/Silver self-play data, build final SFT corpus, train P2S | **No during generation**; base Qwen3.5-9B generates its own training data |
| **2** | SEAL Hackathon + P2S evaluator | **Track A** semantic/deep-state evaluation of P2S, base Qwen, and DeepSeek | **Yes** for the P2S specialist run |
| **3** | AutoRestTest + SEAL | Track A conventional/SOTA baseline | No |
| **4** | CATS + Schemathesis + SEAL | Track A contract/property-based baselines | No |
| **5** | RESTgym 11-service benchmark | **Track B** standardized cross-benchmark | **Yes** |

The model releases are a sixth artifact family used by Operations 2 and 5:

- `minhhungg/qwen35-9b-p2s-lora`
- `minhhungg/qwen35-9b-p2s-merged-4bit`
- `minhhungg/qwen35-9b-p2s-merged-16bit`
- `minhhungg/p2s_gguf`
  - `qwen35-9b-p2s-Q8_0.gguf`
  - `qwen35-9b-p2s-f16.gguf`

---

## 2. Source-of-Truth Rules

The archived experiment notes contain several stale values left over from earlier iterations. For reproducibility, use this priority order:

1. **Final paper / retained run artifacts** for reported experimental settings and numbers.
2. **Target repository branch and retained scripts/artifacts** for exact experiment execution.
3. **P2S Framework v1.1.0** for the normalized reusable proxy/compiler/engine/dataset/analytics behavior.
4. Old scratch commands only when they agree with the above.

### 2.1 Important archival discrepancies

Do not silently reproduce these older draft values:

- **AITasker generation model name:** an old script still contains `Tesslace/Omnicoder-9B-GGUF` as a client-side placeholder. The actual model loaded during the retained AITasker generation run was **base Qwen3.5-9B** through an OpenAI-compatible LM Studio endpoint.
- **AutoRestTest LLM:** an early setup note describes a local base-Qwen value model. The completed run used for the paper is the authoritative run and used **DeepSeek-V4-Flash**.
- **Track B fault detection:** an old helper called mixed-status Goldens “unique 5xx” and reported `33.63/API`. The final status-aware SBFT-aligned value is **321 5xx signatures total / 29.18 per API**.
- **Track B branch coverage:** the old draft used `9%`. The final JaCoCo aggregation is **14.46% mean branch coverage**.
- **Track B efficiency/AUC:** do **not** synthesize P2S AUC values from final snapshots. No P2S Restats metric-time series was retained, so the final paper deliberately leaves official Efficiency/Roadrunner scoring unclaimed.

These distinctions are important: reproducibility means reproducing the final experiment, not reproducing every abandoned intermediate calculation.

---

# Part I — Common Installation

## 3. Host Requirements

The historical runs were primarily developed on Windows 10/11 with Git Bash. Equivalent Linux commands work where paths differ.

Recommended tooling:

- Git + Git Bash on Windows
- Python 3.10+ for P2S Framework; Python 3.12 was used for the AutoRestTest compatibility setup
- Node.js 20+
- npm
- Docker Desktop
- PostgreSQL client tools (`psql`)
- JDK 17 + Maven for SEAL
- CMake + a C/C++ toolchain for llama.cpp
- NVIDIA CUDA toolkit when building llama.cpp with CUDA

Install OCLI and the P2S SDK:

```bash
npm install -g openapi-to-cli

python -m venv .venv
source .venv/Scripts/activate       # Windows Git Bash
# source .venv/bin/activate         # Linux/macOS

pip install --upgrade pip
pip install ./dist/p2s_framework-1.1.0-py3-none-any.whl

p2s --help
ocli --help
```

If working directly from the framework source tree:

```bash
pip install -e .
```

---

## 4. P2S Framework: Historical Script → Public SDK Mapping

The experiments used target-local script names before the framework was packaged. The public SDK maps them as follows:

| Historical file / operation | P2S v1.1.0 replacement |
|---|---|
| `proxy.py` | `p2s.proxy.core_proxy` / `p2s proxy` |
| `trace_compiler.py` | `p2s.compiler.compiler.TraceCompiler` / `p2s compile` / `P2S.compile()` |
| AITasker `eval_student_p2s_engine.py` used for self-play data creation | `p2s.engine.generator.P2SDataGenerator` / `p2s generate-data` |
| SEAL/RESTgym `eval_student_p2s_engine.py` | `p2s.engine.fuzzer.P2SFuzzer` / `p2s fuzz`, plus target-specific research runner where wall-clock control/reset behavior is required |
| dataset dedup/oversampling helper | `p2s.dataset.builder` / `p2s prepare-dataset` |
| cross-run analyzer | `p2s.analytics.analyzer` / `p2s analyze` |
| vector reclassifier | `p2s.analytics.reclassifier` / `p2s reclassify` |
| M1 parser | `p2s.analytics.m1_analyzer` / `p2s m1` |
| false-positive verifier | `p2s.analytics.verifier` / `p2s verify` |

### 4.1 Why some target-specific runners still exist

The public v1.1.0 SDK normalizes the reusable mechanisms, but **the exact Track B experiment has a 3,600-second cyclic wall-clock protocol and per-service reset operations**. Those service-specific resets include SQL reseeding, contract redeployment, MongoDB reseeding, Kafka topic deletion, and container restart. For exact paper parity, preserve the Track B research runner in the RESTgym artifact and use the framework underneath it rather than pretending a single generic TOML can express every one of those operations in v1.1.0.

This is an extension point, not a contradiction: P2S's core generation/execution logic remains the same while state restoration is target-specific.

---

# Part II — P2S Model Download and llama.cpp Serving

## 5. Download the Published Models from Hugging Face

Install the current Hugging Face CLI:

```bash
pip install -U huggingface_hub
hf --help
```

### 5.1 Recommended evaluation artifact: Q8_0 GGUF

```bash
mkdir -p models/p2s

hf download minhhungg/p2s_gguf \
  qwen35-9b-p2s-Q8_0.gguf \
  --local-dir models/p2s
```

Optional F16 GGUF:

```bash
hf download minhhungg/p2s_gguf \
  qwen35-9b-p2s-f16.gguf \
  --local-dir models/p2s
```

### 5.2 Hugging Face-format checkpoints

LoRA adapter only:

```bash
hf download minhhungg/qwen35-9b-p2s-lora \
  --local-dir models/qwen35-9b-p2s-lora
```

Merged 4-bit Transformers checkpoint:

```bash
hf download minhhungg/qwen35-9b-p2s-merged-4bit \
  --local-dir models/qwen35-9b-p2s-merged-4bit
```

Merged 16-bit canonical merge:

```bash
hf download minhhungg/qwen35-9b-p2s-merged-16bit \
  --local-dir models/qwen35-9b-p2s-merged-16bit
```

Use the 16-bit model as the canonical source if you need to perform your own GGUF conversion. The reported evaluation itself used Q8_0 GGUF.

---

## 6. Build llama.cpp with NVIDIA CUDA

```bash
git clone https://github.com/ggml-org/llama.cpp.git
cd llama.cpp

cmake -B build -DGGML_CUDA=ON
cmake --build build --config Release -j 8 --target llama-server
```

Typical binary locations:

```text
Linux / single-config generator:
  build/bin/llama-server

Windows / Visual Studio multi-config build:
  build/bin/Release/llama-server.exe
```

---

## 7. Serve P2S Q8_0 Exactly as the Evaluation Endpoint

The retained paper configuration served the fine-tuned Q8_0 model on port `8081`, fully offloaded to the GPU, with the full 262,144-token context:

### Windows

```bash
./build/bin/Release/llama-server.exe \
  -m ../models/p2s/qwen35-9b-p2s-Q8_0.gguf \
  --host 0.0.0.0 \
  --port 8081 \
  -ngl 99 \
  -c 262144 \
  --threads 8 \
  --alias qwen35-9b-p2s
```

### Linux

```bash
./build/bin/llama-server \
  -m ../models/p2s/qwen35-9b-p2s-Q8_0.gguf \
  --host 0.0.0.0 \
  --port 8081 \
  -ngl 99 \
  -c 262144 \
  --threads 8 \
  --alias qwen35-9b-p2s
```

Verify the OpenAI-compatible service:

```bash
curl http://localhost:8081/v1/models

curl http://localhost:8081/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "qwen35-9b-p2s",
    "messages": [{"role":"user","content":"Return exactly: P2S_READY"}],
    "temperature": 0
  }'
```

P2S config points to it as:

```toml
[llm]
backend = "openai_compat"
base_url = "http://localhost:8081/v1"
model = "qwen35-9b-p2s"
api_key = "no-key"
max_attempts = 6
```

---

# Part III — Operation 1: AITasker Training-Data Generation and Fine-Tuning

## 8. Goal

This operation reproduces the self-play data-creation side of P2S:

```text
AITasker mainflows
    ↓ proxy
primitive_traces.jsonl
    ↓ OpenAPI/OCLI compile
compiled_traces.jsonl + ocli_catalog.json
    ↓ BASE Qwen3.5-9B self-play + execution oracle
raw Golden/Silver JSONL
    ↓ dedup + stratification
final_training_dataset.jsonl
    ↓ response-only LoRA SFT
P2S specialist
```

**Important:** the P2S fine-tuned model is not used to generate its own first training corpus. The retained experiment used **base Qwen3.5-9B** as the generator, then fine-tuned the same architecture on the execution-verified corpus.

---

## 9. Clone the AITasker Research Branch

```bash
git clone https://github.com/alberttrann/AITasker.git
cd AITasker
git switch feat/hung/SWT-Main
```

The archived environment used:

- PostgreSQL: `localhost:5432` for the ordinary AITasker application DB
- FastAPI AI service: `localhost:8000`
- NestJS backend: `localhost:3001`
- trace proxy: `localhost:8090`
- isolated P2S snapshot DB in the historical generator: PostgreSQL on `localhost:5434`, DBs `aitasker_active` / `aitasker_snap`

Do not conflate the ordinary app database with the historical isolated mutation database.

---

## 10. Start AITasker

### Terminal 1 — FastAPI AI service

```bash
cd AITasker/ai-service
python -m venv venv
source venv/Scripts/activate
pip install -r requirements.txt

# Configure .env with your own provider credentials.
# Never commit real API keys.
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://localhost:8000/health
```

### Terminal 2 — NestJS backend

```bash
cd AITasker/backend
npm install
npx prisma generate
npx prisma db push --accept-data-loss

# If this seed exists on the branch:
npx prisma db execute \
  --file=prisma/migrations/010_seed.sql \
  --url="postgresql://postgres:postgres@localhost:5432/aitasker"

npm run build
node dist/main
```

Verify:

```bash
curl http://localhost:3001/health
curl -s http://localhost:3001/api-json -o swagger.json
```

---

## 11. Capture the 20 AITasker Mainflow Scripts

### Historical parity command

The retained development note launches the proxy and then routes all mainflows through it:

```bash
cd AITasker/backend/simulations
TARGET_PORT=3001 LISTEN_PORT=8090 python3 proxy.py
```

In another terminal:

```bash
cd AITasker/backend/simulations/mainflow-validation
BASE_URL=http://localhost:8090 bash run_all_mf.sh
```

The retained experiment produced 48 flow IDs and 520 compiled primitive steps from the 20 scripted journeys.

### Framework-native proxy

For new reproduction runs, prefer P2S Framework's proxy and express the same target in TOML. Example:

```toml
# reproduction/aitasker-training.toml
[target]
name = "aitasker"
base_url = "http://localhost:3001"
openapi_spec = "swagger.json"
state_adapter = "postgres"
executor_adapter = "ocli"
golden_out = "golden_dataset.jsonl"
silver_out = "silver_dataset.jsonl"
checkpoint_file = "processed_flows.txt"

[postgres]
active_db = "aitasker_active"
template_db = "aitasker_snap"
admin_url = "postgresql://postgres:postgres@localhost:5434/postgres"
seed_command = "DATABASE_URL=postgresql://postgres:postgres@localhost:5434/aitasker_active?schema=public npx prisma db push --accept-data-loss && npx prisma db execute --file=prisma/migrations/010_seed.sql --url=postgresql://postgres:postgres@localhost:5434/aitasker_active?schema=public"

[llm]
backend = "openai_compat"
base_url = "http://localhost:1234/v1"
model = "qwen3.5-9b-base"
api_key = "lm-studio"
max_attempts = 6

[proxy]
listen_port = 8090
target_host = "http://localhost:3001"
flow_strategy = "endpoint"
reset_endpoint = "/auth/register"
output_file = "primitive_traces.jsonl"
```

Run:

```bash
p2s proxy --config reproduction/aitasker-training.toml
```

Then execute the same `run_all_mf.sh` against port 8090.

---

## 12. Compile AITasker Traces

Fetch the current OpenAPI document:

```bash
cd AITasker/backend
curl -s -o swagger.json http://localhost:3001/api-json
```

### Historical parity

```bash
python3 simulations/trace_compiler.py
```

### Register OCLI profile

```bash
ocli profiles add aitasker \
  --api-base-url http://localhost:3001 \
  --openapi-spec http://localhost:3001/api-json \
  --api-bearer-token "" \
  --command-prefix ""

ocli use aitasker
```

### Framework-native compiler

If the primitive file, OpenAPI file, and work directory are configured consistently:

```bash
p2s compile \
  --config reproduction/aitasker-training.toml \
  --workdir backend
```

For programmatic control of context-prefix stripping:

```python
from p2s import P2S

sdk = P2S.from_toml("reproduction/aitasker-training.toml", workdir="backend")
sdk.compile(context_path_prefix="")
```

Expected core artifacts:

```text
primitive_traces.jsonl
compiled_traces.jsonl
ocli_catalog.json
```

---

## 13. Serve Base Qwen3.5-9B for Self-Play Generation

The original retained run used base Qwen3.5-9B in LM Studio at an OpenAI-compatible `/v1` endpoint. Any equivalent OpenAI-compatible base-Qwen3.5-9B server is acceptable if the loaded weights are the same.

Example local endpoint:

```text
http://localhost:1234/v1
```

Verify before starting generation:

```bash
curl http://localhost:1234/v1/models
```

Do **not** point this training-generation config at the already fine-tuned P2S GGUF if you are reproducing the original self-improvement cycle.

---

## 14. Generate Execution-Verified Golden/Silver Training Data

### Historical parity

```bash
cd AITasker/backend
python eval_student_p2s_engine.py
```

The historical generator used:

```text
ADMIN_DB_URL   = postgresql://postgres:postgres@localhost:5434/postgres
ACTIVE_DB_NAME = aitasker_active
TEMPLATE_DB    = aitasker_snap
MAX_ATTEMPTS   = 6
```

For each target step it reconstructs prior flow state, snapshots the DB, asks base Qwen for a mutation, executes the OCLI command, and persists the observed outcome.

### Framework-native generation

```bash
p2s generate-data \
  --config reproduction/aitasker-training.toml \
  --workdir backend
```

Equivalent SDK:

```python
from p2s import P2S

sdk = P2S.from_toml("reproduction/aitasker-training.toml", workdir="backend")
generator = sdk.generate_data()
```

Expected raw files:

```text
golden_dataset.jsonl
silver_dataset.jsonl
processed_flows.txt
```

---

## 15. Build the Final SFT Corpus

Run the framework dataset builder:

```bash
p2s prepare-dataset \
  --config reproduction/aitasker-training.toml \
  --workdir backend
```

Or:

```python
from p2s import P2S

sdk = P2S.from_toml("reproduction/aitasker-training.toml", workdir="backend")
sdk.prepare_dataset(
    golden_file="golden_dataset.jsonl",
    silver_file="silver_dataset.jsonl",
    output_file="final_training_dataset.jsonl",
    max_seq_length=24576,
    seed=3407,
)
```

The final retained corpus should be compared against the paper's accounting:

```text
Raw Silver             1,917
Deduplicated Silver    1,782
Unique Golden             44
Golden oversampled 10x   440
Golden reinforcement      44
Final SFT samples       2,266
```

If your rerun differs, report the rerun as a new repetition rather than editing artifacts to force the historical counts.

---

## 16. Reproduce Fine-Tuning with the Root Colab Notebook

The public P2S repository includes a **root-level Google Colab notebook** (`p2s_colab_train.ipynb`) to reproduce the model-training stage from the dataset emitted by the framework.

> **Scope boundary:** this notebook is **not part of the official P2S SDK/runtime**. `pip install p2s-framework` gives you the reusable capture/compile/fuzz/data-generation/dataset tooling. The notebook is a separate research-reproduction convenience that consumes the framework's final JSONL output. It is intentionally not imported by `p2s`, not required by the CLI, and does not make Unsloth/TRL runtime dependencies of the SDK.

The clean interface between the two layers is:

```text
P2S framework
    │
    ├─ primitive_traces.jsonl
    ├─ compiled_traces.jsonl
    ├─ golden_dataset.jsonl
    ├─ silver_dataset.jsonl
    │
    └─ p2s prepare-dataset
           │
           ▼
final_training_dataset.jsonl
           │
           │  only required training-data input
           ▼
root p2s_colab_train.ipynb
           │
           ├─ LoRA adapter
           ├─ merged 16-bit checkpoint
           └─ merged 4-bit checkpoint
                    │
                    └─ separate llama.cpp conversion -> F16 / Q8_0 GGUF
```

### 16.1 Prepare the Notebook Input

First generate the final training corpus with the framework as described in the previous section. For the historical run, the retained final corpus contains **2,266 records**.

The notebook expects this exact filename in its working directory:

```text
final_training_dataset.jsonl
```

In Colab, the simplest paper-parity path is to upload/copy it to:

```text
/content/final_training_dataset.jsonl
```

The notebook deliberately checks for the file at startup and fails early if it is missing, rather than silently training on another dataset.

### 16.2 Select the Colab Runtime

For the reported run, use:

```text
Google Colab
GPU: NVIDIA A100 80 GB
```

An A100 is an **experiment-parity recommendation**, not a requirement of the P2S framework itself. The SDK can generate the JSONL independently of the hardware used later for model training.

### 16.3 Install Notebook-Only Dependencies

Run the dependency cell near the top of the notebook:

```python
!pip install unsloth trl datasets
```

These are training-notebook dependencies only. They are intentionally not required for normal `p2s-framework` installation.

### 16.4 Review the Notebook Configuration

The notebook's important defaults are:

```text
Input file               final_training_dataset.jsonl
Base model               unsloth/Qwen3.5-9B
Model loading            4-bit
Maximum sequence length  24,576
LoRA rank                32
LoRA alpha               64
LoRA dropout             0.05
Vision layers            excluded
Language layers          trained
Attention modules        trained
MLP modules              trained
Target modules           q/k/v/o + gate/up/down + lm_head + embed_tokens
Gradient checkpointing   Unsloth
Random seed              3407
Output root              /content/p2s-outputs
Checkpoint directory     /content/p2s-outputs/qwen35-9b-checkpoints
```

Hugging Face upload is optional and controlled independently:

```python
PUSH_TO_HUB = False
HF_TOKEN = os.environ.get("HF_TOKEN", "your_hf_token_here")
HF_USER = "your-username"
```

Set `PUSH_TO_HUB = True` only when you intentionally want the notebook to upload the resulting artifacts.

### 16.5 Run the Dataset Audit Before Training

The notebook loads the JSONL with `datasets.load_dataset`, converts each `messages` conversation through the Qwen chat template, and scans the entire corpus before the trainer starts.

It prints:

```text
Train Samples
P50 token length
P90 token length
P99 token length
Maximum token length
number of samples exceeding 24,576 tokens
```

For the retained paper run, the measured pre-tokenization distribution was:

```text
P50    4,079
P90   10,679
P99   16,757
max   17,965
```

Therefore no retained training record exceeded the configured 24,576-token limit.

If a future regenerated corpus does exceed the limit, do **not** hide the warning. Record the new distribution and describe the truncation/configuration decision as part of that new experimental repetition.

### 16.6 Response-Only Training

The notebook constructs `SFTTrainer`, then applies:

```python
trainer = train_on_responses_only(
    trainer,
    instruction_part="<|im_start|>user\n",
    response_part="<|im_start|>assistant\n",
)
```

This masks system/user prompt and state-history tokens with `-100`, so supervised loss is applied only to the assistant response.

The notebook immediately verifies this behavior on a real dataloader batch and prints the masked-vs-response token ratio. This is a useful reproducibility guard: a broken chat boundary could otherwise silently produce either no trainable response tokens or loss on the entire prompt/history.

### 16.7 Trainer Configuration

The retained training configuration is:

```text
Per-device batch size      1
Gradient accumulation      4
Effective batch size       4
Warmup steps               50
Epochs                     6
Learning rate              2e-4
Precision                  bfloat16
FP16                       disabled
Optimizer                  AdamW 8-bit
Weight decay               0.01
Scheduler                   cosine_with_restarts
LR cycles                  6
Maximum gradient norm      1.0
NEFTune noise alpha        5.0
Packing                    disabled
Checkpoint every           100 steps
Retained checkpoints       3
```

The notebook exposes:

```python
RESUME_FROM_CHECKPOINT = False
```

Set it to `True` when resuming from a retained checkpoint directory rather than starting a new run.

### 16.8 Pre-Training GPU Health Probe

Before committing to the full multi-hour run, the notebook executes a synthetic 512-token forward/backward pass under bfloat16 autocast and prints the loss and timing.

This verifies, before `trainer.train()`, that:

- the model is actually on the GPU;
- the forward pass produces a finite loss;
- gradients flow through the LoRA-adapted model; and
- the dtype/runtime configuration is usable.

This is especially important for expensive A100 runs because it catches environment and masking problems before hours of compute are spent.

### 16.9 Execute the Full Training Run

Run the notebook cells top-to-bottom and then execute:

```python
trainer_stats = trainer.train(resume_from_checkpoint=RESUME_FROM_CHECKPOINT)
```

For the retained run, the paper records:

```text
Optimization steps        3,402
Trainable parameters      58,195,968
Total parameters          9,468,009,712
Fraction adapted          0.61%
Final reported loss       0.1418
Peak reserved GPU memory  34.69 GB
Runtime                    about 8.3 hours
```

A new run does not need to reproduce every stochastic number bit-for-bit. Preserve its logs and report it as a new repetition if it differs.

### 16.10 Notebook Outputs

By default the notebook writes to:

```text
/content/p2s-outputs/
├── qwen35-9b-p2s-lora/
├── qwen35-9b-p2s-merged-16bit/
├── qwen35-9b-p2s-merged-4bit/
└── qwen35-9b-checkpoints/
```

The notebook verifies the saved directories and reports file counts/sizes at the end.

Expected public artifact roles are:

```text
LoRA adapter       -> minhhungg/qwen35-9b-p2s-lora
Merged 4-bit       -> minhhungg/qwen35-9b-p2s-merged-4bit
Merged 16-bit      -> minhhungg/qwen35-9b-p2s-merged-16bit
```

### 16.11 GGUF Is a Separate Post-Training Step

The Colab notebook does **not** define the official P2S runtime and does not need to produce the evaluation GGUF itself. For the reported evaluation, the merged 16-bit checkpoint is converted separately with llama.cpp:

```bash
python convert_hf_to_gguf.py <MERGED_16BIT_DIR> \
  --outfile qwen35-9b-p2s-f16.gguf \
  --outtype f16

./llama-quantize \
  qwen35-9b-p2s-f16.gguf \
  qwen35-9b-p2s-Q8_0.gguf \
  Q8_0
```

The public GGUF repository is:

```text
minhhungg/p2s_gguf
```

and contains the F16 and Q8_0 forms used for local llama.cpp deployment.

### 16.12 What to Retain for Reproducibility

For a complete model-training reproduction, retain at minimum:

```text
p2s_colab_train.ipynb
final_training_dataset.jsonl
training stdout / notebook cell outputs
checkpoint metadata or final trainer metrics
qwen35-9b-p2s-lora/
qwen35-9b-p2s-merged-16bit/
qwen35-9b-p2s-merged-4bit/
GGUF conversion command + llama.cpp revision
qwen35-9b-p2s-f16.gguf or HF repository reference
qwen35-9b-p2s-Q8_0.gguf or HF repository reference
```

The important methodological boundary is that the **dataset is produced by P2S**, while the **notebook is one reproducible consumer of that dataset for the specific Qwen3.5-9B specialization reported in this study**. A future user may train another architecture from the same JSONL without changing the P2S framework itself.

---

# Part IV — Track A Full-Fidelity Reproduction

The previous condensed Track-A recipe has been replaced by a full-fidelity protocol. **The normative reviewer-facing procedure is [`docs/TRACK_A_SEAL_FULL_FIDELITY.md`](TRACK_A_SEAL_FULL_FIDELITY.md)**, and executable historical-parity helpers live in [`docs/track_a_helpers/`](track_a_helpers/).

Track A is intentionally split into four executions rather than collapsed into a generic benchmark command:

1. P2S fine-tuned Qwen3.5-9B through the archived SEAL evaluator;
2. untuned Qwen3.5-9B and DeepSeek through the same P2S evaluator path;
3. AutoRestTest on the baseline-favourable sanitized target;
4. CATS and Schemathesis on that same baseline-favourable target.

## 17. SEAL target bootstrap

Use the retained SEAL research branch, PostgreSQL dump, and migrations. Recreate the database with separate drop/create operations, apply all three gap-fill migrations, build the standalone JAR, and launch it with a fixed test-only JWT secret. The exact commands and filenames are in the dedicated Track-A guide.

## 18. P2S trace capture is header-tagged and stateful

For historical parity use:

```bash
python docs/track_a_helpers/proxy_seal_historical.py
BASE_URL=http://localhost:8090/api bash docs/track_a_helpers/seal_flows_historical.sh
```

The proxy uses `X-Flow-ID`, per-flow atomic counters, sensitive-header masking, and health-check suppression. The flow script encodes the application-state rules needed to produce valid 21-flow traces.

## 19. Use the historical SEAL compiler for retained-result parity

```bash
curl -s http://localhost:8080/api/v3/api-docs -o swagger.json
python docs/track_a_helpers/trace_compiler_seal_historical.py
```

The compiler strips `/api`, skips malformed `//` paths, preserves the historical OCLI naming rule, resolves single-level `$ref` query types, and emits the richer `seal_ocli_catalog.json`.

## 20. Historical evaluator parity is stricter than `p2s fuzz`

```bash
python docs/track_a_helpers/eval_student_p2s_engine_historical_sanitized.py
```

The retained evaluator includes Windows/Qwen runtime patches, multi-format response parsing, 24,576-token generation, 150-second OCLI timeout, command normalization, object-query repair, automatic Coordinator token/profile refresh, OCLI profile auto-registration, required-constraint relaxation, PostgreSQL snapshot retries, and per-backend artifact prefixes. Those are part of the historical experiment path.

Run the P2S specialist, untuned Qwen, and DeepSeek as separate backends while keeping traces/catalog/reset/attempt budget fixed.

## 21. Track-A post-hoc semantic verification

```bash
python docs/track_a_helpers/validate_seal_goldens.py --golden-file llamacpp_golden_dataset.jsonl --output-verified llamacpp_verified_goldens.jsonl
python docs/track_a_helpers/deduplicate_goldens.py llamacpp_verified_goldens.jsonl
python docs/track_a_helpers/reclassify_vectors.py llamacpp both
```

Candidate labels do not become security claims until the verifier removes CLI-help bleed, Jackson-ignored pseudo mass assignment, and ordinary authorized 2xx outcomes lacking identity/resource mutation.

## 22. Conventional-baseline shared target preparation

For AutoRestTest, CATS, and Schemathesis, extend the access-token lifetime to **525,600 minutes**, use a stable test-only signing secret, clear `revoked_tokens`, mint a fresh Coordinator token from the currently running backend, and sanitize the live OpenAPI document:

```bash
curl -s http://localhost:8080/api/v3/api-docs -o seal_openapi.json
python docs/track_a_helpers/sanitize_baseline_openapi.py seal_openapi.json
python docs/track_a_helpers/verify_long_lived_jwt.py
```

The sanitized contract fixes the server URL and removes `/auth/logout` plus user self-deletion. No custom producer-consumer/state hints are added.

## 23. AutoRestTest parity

Retain the archived Python-3.12 compatibility environment when reproducing that revision. Use `strict_validation=false`, disable the Header Agent, disable graph/Q-table caches, retain the 15 ms Windows dispatcher throttle, and run the request-generation phase for 18,000 seconds:

```bash
python -m autoresttest.autoresttest --skip-wizard
```

**Completed-run parity uses DeepSeek-V4-Flash**, even though an earlier setup template in the note mentions local base Qwen. Preserve the complete `data/seal_openapi/` directory and audit persisted records with:

```bash
python /path/to/p2s/source/docs/track_a_helpers/autoresttest_posthoc_audit.py --server-errors data/seal_openapi/server_errors.json
```

## 24. CATS and Schemathesis parity

Use the same sanitized OpenAPI + fresh long-lived Coordinator token.

```bash
COORD_TOKEN=$(cat cats_jwt.txt)
./cats.exe --contract seal_openapi.json --server http://localhost:8080/api -H "Authorization=Bearer ${COORD_TOKEN}" --output cats_report

schemathesis run seal_openapi.json \
  --url http://localhost:8080/api \
  -H "Authorization: Bearer ${COORD_TOKEN}" \
  --checks all --max-examples 100 \
  --report-junit-path schemathesis_report.xml \
  --report-vcr-path schemathesis_vcr.yaml
```

Then run:

```bash
python /path/to/p2s/source/docs/track_a_helpers/cats_schemathesis_posthoc_audit.py
```

Keep native 5xx/error counters distinct from independently verified authorization/lifecycle outcomes.

## 25. Track-A source-of-truth note

The dedicated guide documents every known supersession: most importantly the AutoRestTest base-Qwen setup template versus the completed DeepSeek-V4-Flash run, the invalid fall-through interpretation of early AutoRestTest keyword buckets, and the distinction between engine candidate goldens and validated outcomes.

---

# Part VII — Operation 5: Track B on the 11 SBFT RESTgym Services

## 34. Clone and Initialize RESTgym

```bash
git clone https://github.com/restgym/restgym.git
cd restgym
```

Windows Git Bash normalization used by the retained runs:

```bash
git config --global url."https://github.com/".insteadOf "git@github.com:"
git config --global core.autocrlf input

git submodule update --init --recursive
find . -type f -name "*.sh" -exec sed -i 's/\r$//' {} +
```

Create environment:

```bash
python -m venv venv
source venv/Scripts/activate

export MSYS_NO_PATHCONV=1
export PYTHONUNBUFFERED=1

pip install --only-binary=:all: "zstandard>=0.22.0"
pip install --prefer-binary -r src/requirements.txt
pip install openai httpx requests pyyaml psycopg2-binary numpy pandas tabulate

# Install P2S Framework as well:
pip install /path/to/p2s_framework-1.1.0-py3-none-any.whl

python -c "import openai,httpx,requests,yaml,psycopg2,numpy,pandas,tabulate,p2s; print('Environment ready')"
```

Serve the P2S Q8_0 GGUF on port `8081` before starting any service run.

---

## 35. Track B Exact Experimental Shape — Phase 1 Is Normative

The service-specific **Phase 1 environment is part of the experiment**, not disposable setup boilerplate. A faithful rerun must preserve the RESTgym configuration patches, authentication/proxy behavior, context paths, container launch parameters, and reset primitive that made each evaluated service reachable in the same operational state. Applying only the generic compiler/evaluator commands is insufficient.

In particular:

- apply source/config patches **before the Docker image is built** whenever the patched file is copied into that image;
- keep trace recording and P2S evaluation behind RESTgym port `9090` when the proxy supplies authentication or path rewriting;
- keep JaCoCo on `12345` and the retained `API=<service>`, `TOOL=manual`, `RUN=1` launch contract;
- preserve the original state-reset mechanism rather than silently replacing SQL reseed, contract redeploy, Mongo reseed, topic deletion, or restart with a different reset;
- where the retained source gives an exact patch command, reproduce it; where only the required adapter behavior survives in the paper/research artifact, state that behavior explicitly rather than inventing a replacement command.

For each service:

1. Prepare/patch the RESTgym service.
2. Build and start its container.
3. Record a deterministic valid lifecycle trace through port `9090`.
4. Compile the trace against that service's OpenAPI specification.
5. Execute the fine-tuned P2S research runner for **3,600 seconds**.
6. Deduplicate **status-500-only** Goldens for SBFT Fault Detection.
7. Retain Golden/Silver JSONL and run metadata.
8. Dump JaCoCo from port `12345` into `results/<service>/code-coverage/coverage.csv` (or normalize to the published `code-coverage.csv` filename in the artifact).
9. Do not synthesize P2S AUC from the final snapshot.

The historical parity command shape is:

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

python dedup_p2s_goldens.py <service>_p2s_golden_dataset.jsonl
python reclassify_vectors.py <service>_p2s both
```

### Framework relationship

`trace_compiler.py` and `eval_student_p2s_engine.py` in the Track B artifact are target/research wrappers around the same responsibilities now public as `p2s.compiler` and `p2s.engine`. Keep them in the Track B release because v1.1.0 does not yet encode the paper's per-service reset commands and hard 3,600-second cyclic budget as generic TOML fields.

---

## 36. Service 1 — `blog-api`

### Phase 1 — Configuration / auth / proxy contract and container launch

The retained run uses the RESTgym proxy on `9090` in front of the Spring/MySQL service. No additional source patch is documented for this service, but the proxy port, environment variables, startup wait, and SQL reseed are still part of the evaluated environment.


```bash
docker build -t restgym/blog:latest -f apis/blog/Dockerfile .
docker rm -f restgym_blog 2>/dev/null || true

MSYS_NO_PATHCONV=1 docker run -d --name restgym_blog \
  -p 9090:9090 -p 12345:12345 \
  -e API=blog -e TOOL=manual -e RUN=1 \
  restgym/blog:latest
sleep 15
```

### Phase 2 — Trace recording

```text
record_blog_full_52.py
```

Run:

```bash
python record_blog_full_52.py
```

Expected trace:

```text
p2s_traces/blog/primitive_traces.jsonl
```

### Phase 3 — Trace compilation


```bash
python3 trace_compiler.py \
  --swagger apis/blog/specifications/blog.yaml \
  --input p2s_traces/blog/primitive_traces.jsonl \
  --output p2s_traces/blog/compiled_traces.jsonl \
  --catalog p2s_traces/blog/blog_ocli_catalog.json
```

### Phase 4 — 3,600-second P2S execution


```bash
rm -f blog_p2s_golden_dataset.jsonl blog_p2s_silver_dataset.jsonl blog_p2s_processed_flows.txt

python3 eval_student_p2s_engine.py \
  --target-port 9090 \
  --traces p2s_traces/blog/compiled_traces.jsonl \
  --catalog p2s_traces/blog/blog_ocli_catalog.json \
  --output-prefix blog_p2s \
  --time-budget 3600
```

### Phase 5 — State reset contract

State reset used by the runner:

```bash
docker exec restgym_blog mysql -ublog -pblog blogapi < apis/blog/database/blogapi.sql
```

### Phase 6 — JaCoCo coverage extraction

Coverage:

```bash
MSYS_NO_PATHCONV=1 docker exec restgym_blog bash -c '
  mkdir -p /results/blog/manual/1/code-coverage
  JACOCO_JAR=$(find /infrastructure/jacoco -name "org.jacoco.cli-*.jar" | head -n 1)
  java -jar $JACOCO_JAR dump --address localhost --port 12345 --destfile /results/blog/manual/1/code-coverage/jacoco.exec
  if [ -d "/api/classes" ] && [ "$(ls -A /api/classes)" ]; then CLASS_LOCATION="/api/classes"; else CLASS_LOCATION=$(find /api -name "*.jar" | head -n 1); fi
  java -jar $JACOCO_JAR report /results/blog/manual/1/code-coverage/jacoco.exec --classfiles "$CLASS_LOCATION" --csv /results/blog/manual/1/code-coverage/coverage.csv
'
mkdir -p results/blog/code-coverage
MSYS_NO_PATHCONV=1 docker cp restgym_blog:/results/blog/manual/1/code-coverage/coverage.csv results/blog/code-coverage/coverage.csv
```

---

## 37. Service 2 — `erc20-api`

### Phase 1 — Configuration / auth / proxy contract and container launch

This Phase 1 is mandatory. The retained Dockerfile needs the `/logs` directory created before Spring writes to it. The container combines Ganache, Spring Boot, and the RESTgym/mitmproxy layer, so the retained launch uses a 6 GB memory allowance. The RESTgym `auth.py`/mitmproxy path rewrite is also semantically required: requests carry a dummy contract address and the proxy rewrites it to the **currently deployed** contract. Bypassing `9090` removes that behavior and is not equivalent to the retained run.

Patch the Dockerfile so the log directory exists before Spring writes to it, then build:

```bash
python3 - <<'PY'
p="apis/erc20/Dockerfile"
s=open(p,encoding="utf-8").read()
s=s.replace(
    "mkdir -p /results/$API/$TOOL/$RUN/code-coverage\\n\\",
    "mkdir -p /results/$API/$TOOL/$RUN/code-coverage /results/$API/$TOOL/$RUN/logs\\n\\",
)
open(p,"w",encoding="utf-8").write(s)
PY

docker rm -f restgym_erc20 2>/dev/null || true
docker build -t restgym/erc20:latest -f apis/erc20/Dockerfile .

MSYS_NO_PATHCONV=1 docker run -d --name restgym_erc20 \
  --memory=6g \
  -p 9090:9090 -p 12345:12345 \
  -e API=erc20 -e TOOL=manual -e RUN=1 \
  restgym/erc20:latest
sleep 25
```

### Phase 2 — Trace recording


```text
record_erc20_full_13.py
```

```bash
python record_erc20_full_13.py
```

### Phase 3 — Trace compilation


```bash
python3 trace_compiler.py \
  --swagger apis/erc20/specifications/erc20.yaml \
  --input p2s_traces/erc20/primitive_traces.jsonl \
  --output p2s_traces/erc20/compiled_traces.jsonl \
  --catalog p2s_traces/erc20/erc20_ocli_catalog.json
```

### Phase 4 — 3,600-second P2S execution


```bash
rm -f erc20_p2s_golden_dataset.jsonl erc20_p2s_silver_dataset.jsonl erc20_p2s_processed_flows.txt
python3 eval_student_p2s_engine.py \
  --target-port 9090 \
  --traces p2s_traces/erc20/compiled_traces.jsonl \
  --catalog p2s_traces/erc20/erc20_ocli_catalog.json \
  --output-prefix erc20_p2s \
  --time-budget 3600
```

### Phase 5 — State reset contract

Fast state reset:

```bash
docker exec restgym_erc20 python3 /api/init-contract.py
```

The RESTgym proxy rewrites the dummy contract address to the newly deployed contract. **Keep the proxy active during every reset and subsequent mutation.**

### Phase 6 — JaCoCo application-class extraction

For coverage, extract only `BOOT-INF/classes` from the application JAR to avoid duplicate third-party/Lombok classes before running JaCoCo report generation.

---

## 38. Service 3 — `features-service`

### Phase 1 — Configuration / auth / proxy contract and container launch

`restgym-api-config.yml` is disabled by default in the retained setup. Set `enabled: true` **before building**. Without that enablement the RESTgym entrypoint can skip the mitmproxy path on `9090`, so a directly reachable backend would still not reproduce the evaluated P2S route. The `requires` / `excludes` operations also require `application/x-www-form-urlencoded` payloads and must not be silently rewritten as JSON.

Enable the service **before building**:

```bash
echo "enabled: true" > apis/features-service/restgym-api-config.yml
```

Build/run:

```bash
docker rm -f restgym_features_service 2>/dev/null || true
docker build -t restgym/features-service:latest -f apis/features-service/Dockerfile .
MSYS_NO_PATHCONV=1 docker run -d --name restgym_features_service \
  -p 9090:9090 -p 12345:12345 \
  -e API=features-service -e TOOL=manual -e RUN=1 \
  restgym/features-service:latest
sleep 12
```

### Phase 2 — Trace recording


```text
record_features_full_18.py
```

The `requires` / `excludes` constraint endpoints must preserve `application/x-www-form-urlencoded` bodies.

```bash
python record_features_full_18.py

python3 trace_compiler.py \
  --swagger apis/features-service/specifications/features-service.yaml \
  --input p2s_traces/features-service/primitive_traces.jsonl \
  --output p2s_traces/features-service/compiled_traces.jsonl \
  --catalog p2s_traces/features-service/features_service_ocli_catalog.json

rm -f features_service_p2s_processed_flows.txt features_service_p2s_golden_dataset.jsonl features_service_p2s_silver_dataset.jsonl
python3 eval_student_p2s_engine.py \
  --target-port 9090 \
  --traces p2s_traces/features-service/compiled_traces.jsonl \
  --catalog p2s_traces/features-service/features_service_ocli_catalog.json \
  --output-prefix features_service_p2s \
  --time-budget 3600
```

### Phase 5 — State reset contract

Reset:

```bash
docker restart restgym_features_service
```

---

## 39. Service 4 — `flight-search-api`

### Phase 1 — Configuration / auth / proxy contract and container launch

Patch RESTgym authentication **before the Docker build** so the image registers an `ADMIN` identity rather than the default `USER`. The protected airport/flight lifecycle depends on that privilege. Trace recording and P2S evaluation must stay behind the authenticated RESTgym proxy on `9090`. On Windows, the retained reset implementation should suppress subprocess output with `subprocess.DEVNULL` rather than Linux-only `>/dev/null 2>&1` when commands are executed through `cmd.exe`.

Patch RESTgym authentication to register an ADMIN test identity **before building**:

```bash
python3 - <<'PY'
p="apis/flight-search/auth.py"
s=open(p,encoding="utf-8").read()
s=s.replace('"userType": "USER"','"userType": "ADMIN"').replace('test@example.com','admin@example.com')
open(p,"w",encoding="utf-8").write(s)
PY
```

Build/run:

```bash
docker rm -f restgym_flightsearch 2>/dev/null || true
docker build -t restgym/flightsearch:latest -f apis/flight-search/Dockerfile .
MSYS_NO_PATHCONV=1 docker run -d --name restgym_flightsearch \
  -p 9090:9090 -p 12345:12345 \
  -e API=flight-search -e TOOL=manual -e RUN=1 \
  restgym/flightsearch:latest
sleep 35
```

### Phase 2 — Trace recording


```text
record_flightsearch_full_40.py
```

### Phase 3 — OpenAPI acquisition and trace compilation


```bash
python record_flightsearch_full_40.py
mkdir -p p2s_traces/flight-search
MSYS_NO_PATHCONV=1 docker cp restgym_flightsearch:/api/specifications/flight-search.yaml p2s_traces/flight-search/flightsearch.yaml

python3 trace_compiler.py \
  --swagger p2s_traces/flight-search/flightsearch.yaml \
  --input p2s_traces/flight-search/primitive_traces.jsonl \
  --output p2s_traces/flight-search/compiled_traces.jsonl \
  --catalog p2s_traces/flight-search/flightsearch_ocli_catalog.json
```

### Phase 4 — 3,600-second P2S execution


```bash
rm -f flightsearch_p2s_processed_flows.txt flightsearch_p2s_golden_dataset.jsonl flightsearch_p2s_silver_dataset.jsonl
python3 eval_student_p2s_engine.py \
  --target-port 9090 \
  --traces p2s_traces/flight-search/compiled_traces.jsonl \
  --catalog p2s_traces/flight-search/flightsearch_ocli_catalog.json \
  --output-prefix flightsearch_p2s \
  --time-budget 3600
```

### Phase 5 — State reset contract

Fast reset:

```bash
docker exec restgym_flightsearch mongosh flightdatabase --eval 'db.dropDatabase();'
docker exec restgym_flightsearch mongosh flightdatabase /api/database/init-mongo.js
```

---

## 40. Service 5 — `gestao-hospital-api`

### Phase 1 — Configuration / auth / proxy contract and container launch

The retained Track-B adapter includes **session-cookie auto-authentication** plus a fast MongoDB drop/reseed. That authentication behavior belongs to the RESTgym proxy environment. Record and evaluate through `localhost:9090`; do not replace it with unauthenticated direct backend traffic. The exact historical source-level cookie patch command is not preserved in this framework release, so this guide records the required behavior instead of fabricating a substitute.

All requests used for trace/evaluation should continue through `9090` so the session-cookie hook remains active.

```bash
docker rm -f restgym_gestaohospital 2>/dev/null || true
docker build -t restgym/gestaohospital:latest -f apis/gestao-hospital/Dockerfile .
MSYS_NO_PATHCONV=1 docker run -d --name restgym_gestaohospital \
  -p 9090:9090 -p 12345:12345 \
  -e API=gestao-hospital -e TOOL=manual -e RUN=1 \
  restgym/gestaohospital:latest
sleep 20
```

### Phase 2 — Trace recording


```text
record_gestao_full_20.py
```

### Phase 2–4 — Record, compile, and execute the 3,600-second run


```bash
python record_gestao_full_20.py
mkdir -p p2s_traces/gestao-hospital
cp apis/gestao-hospital/specifications/gestao-hospital-openapi.json p2s_traces/gestao-hospital/gestaohospital.json

python3 trace_compiler.py \
  --swagger p2s_traces/gestao-hospital/gestaohospital.json \
  --input p2s_traces/gestao-hospital/primitive_traces.jsonl \
  --output p2s_traces/gestao-hospital/compiled_traces.jsonl \
  --catalog p2s_traces/gestao-hospital/gestaohospital_ocli_catalog.json

rm -f gestaohospital_p2s_processed_flows.txt gestaohospital_p2s_golden_dataset.jsonl gestaohospital_p2s_silver_dataset.jsonl
python3 eval_student_p2s_engine.py \
  --target-port 9090 \
  --traces p2s_traces/gestao-hospital/compiled_traces.jsonl \
  --catalog p2s_traces/gestao-hospital/gestaohospital_ocli_catalog.json \
  --output-prefix gestaohospital_p2s \
  --time-budget 3600
```

### Phase 5 — State reset contract

Fast reset:

```bash
docker exec restgym_gestaohospital mongosh HospitalDB --eval 'db.dropDatabase();'
docker exec restgym_gestaohospital mongosh HospitalDB /api/database/init-mongo.js
```

---

## 41. Service 6 — `kafka-rest-proxy-api`

### Phase 1 — Configuration / auth / proxy contract and container launch

Launch the complete Kafka KRaft / Schema Registry / REST Proxy stack and wait for readiness before recording. The state adapter deliberately resets only the target topic rather than restarting the entire stack.

```bash
docker rm -f restgym_kafkarest 2>/dev/null || true
docker build -t restgym/kafkarest:latest -f apis/kafka-rest-proxy/Dockerfile .
MSYS_NO_PATHCONV=1 docker run -d --name restgym_kafkarest \
  -p 9090:9090 -p 12345:12345 \
  -e API=kafka-rest-proxy -e TOOL=manual -e RUN=1 \
  restgym/kafkarest:latest
sleep 30
```

### Phase 2 — Trace recording


```text
record_kafkarest_full_50.py
```

### Phase 2–4 — Record, compile, and execute the 3,600-second run


```bash
python record_kafkarest_full_50.py
mkdir -p p2s_traces/kafka-rest-proxy
cp apis/kafka-rest-proxy/specifications/* p2s_traces/kafka-rest-proxy/
SPEC_FILE=$(ls p2s_traces/kafka-rest-proxy/*.yaml p2s_traces/kafka-rest-proxy/*.json 2>/dev/null | head -n 1)

python3 trace_compiler.py \
  --swagger "$SPEC_FILE" \
  --input p2s_traces/kafka-rest-proxy/primitive_traces.jsonl \
  --output p2s_traces/kafka-rest-proxy/compiled_traces.jsonl \
  --catalog p2s_traces/kafka-rest-proxy/kafkarest_ocli_catalog.json

rm -f kafkarest_p2s_processed_flows.txt kafkarest_p2s_golden_dataset.jsonl kafkarest_p2s_silver_dataset.jsonl
python3 eval_student_p2s_engine.py \
  --target-port 9090 \
  --traces p2s_traces/kafka-rest-proxy/compiled_traces.jsonl \
  --catalog p2s_traces/kafka-rest-proxy/kafkarest_ocli_catalog.json \
  --output-prefix kafkarest_p2s \
  --time-budget 3600
```

### Phase 5 — State reset contract

Fast reset:

```bash
docker exec restgym_kafkarest kafka-topics \
  --bootstrap-server localhost:9092 \
  --delete --topic p2s-topic
```

### Phase 6 — JaCoCo class scope

JaCoCo needs to target the Confluent application classes (for example `io/confluent/**`) rather than unrelated dependencies.

---

## 42. Service 7 — `market-api`

### Phase 1 — Configuration / auth / proxy contract and container launch

Enable the service before building and preserve the retained **session-cookie authentication** through RESTgym port `9090`. A direct unauthenticated call to the backend is a different experiment. The exact historical cookie-hook patch command is not reconstructed in this framework release; the required auth behavior is therefore stated explicitly rather than replaced with an invented command.

Enable before build:

```bash
echo "enabled: true" > apis/market/restgym-api-config.yml

docker rm -f restgym_market 2>/dev/null || true
docker build -t restgym/market:latest -f apis/market/Dockerfile .
MSYS_NO_PATHCONV=1 docker run -d --name restgym_market \
  -p 9090:9090 -p 12345:12345 \
  -e API=market -e TOOL=manual -e RUN=1 \
  restgym/market:latest
sleep 15
```

### Phase 2 — Trace recording


```text
record_market_full_13.py
```

```bash
python record_market_full_13.py
mkdir -p p2s_traces/market
cp apis/market/specifications/market.yaml p2s_traces/market/market.yaml

python3 trace_compiler.py \
  --swagger p2s_traces/market/market.yaml \
  --input p2s_traces/market/primitive_traces.jsonl \
  --output p2s_traces/market/compiled_traces.jsonl \
  --catalog p2s_traces/market/market_ocli_catalog.json

rm -f market_p2s_processed_flows.txt market_p2s_golden_dataset.jsonl market_p2s_silver_dataset.jsonl
python3 eval_student_p2s_engine.py \
  --target-port 9090 \
  --traces p2s_traces/market/compiled_traces.jsonl \
  --catalog p2s_traces/market/market_ocli_catalog.json \
  --output-prefix market_p2s \
  --time-budget 3600
```

### Phase 5 — State reset contract

Reset:

```bash
docker restart restgym_market
```

---

## 43. Service 8 — `notebook-manager-api`

### Phase 1 — Configuration / auth / proxy contract and container launch

Enable the service before building. The retained adapter uses MySQL **schema/data SQL re-import** for fast state reset. Preserve the research branch's reset helper verbatim when available; do not silently substitute a container restart simply because it is easier.

```bash
echo "enabled: true" > apis/notebook-manager/restgym-api-config.yml

docker rm -f restgym_notebookmanager 2>/dev/null || true
docker build -t restgym/notebookmanager:latest -f apis/notebook-manager/Dockerfile .
MSYS_NO_PATHCONV=1 docker run -d --name restgym_notebookmanager \
  -p 9090:9090 -p 12345:12345 \
  -e API=notebook-manager -e TOOL=manual -e RUN=1 \
  restgym/notebookmanager:latest
sleep 15
```

### Phase 2 — Trace recording


```text
record_notebookmanager_full_5.py
```

```bash
python record_notebookmanager_full_5.py
mkdir -p p2s_traces/notebook-manager
cp apis/notebook-manager/specifications/notebook-manager.yaml p2s_traces/notebook-manager/notebookmanager.yaml

python3 trace_compiler.py \
  --swagger p2s_traces/notebook-manager/notebookmanager.yaml \
  --input p2s_traces/notebook-manager/primitive_traces.jsonl \
  --output p2s_traces/notebook-manager/compiled_traces.jsonl \
  --catalog p2s_traces/notebook-manager/notebookmanager_ocli_catalog.json

rm -f notebookmanager_p2s_processed_flows.txt notebookmanager_p2s_golden_dataset.jsonl notebookmanager_p2s_silver_dataset.jsonl
python3 eval_student_p2s_engine.py \
  --target-port 9090 \
  --traces p2s_traces/notebook-manager/compiled_traces.jsonl \
  --catalog p2s_traces/notebook-manager/notebookmanager_ocli_catalog.json \
  --output-prefix notebookmanager_p2s \
  --time-budget 3600
```

### Phase 5 — MySQL SQL re-import reset contract

The retained Track B adapter uses fast SQL schema/data re-import for state reset. If the published local branch has that reset helper, preserve it verbatim and invoke it through the research runner rather than silently replacing it with a slower container restart.

---

## 44. Service 9 — `person-controller-api`

### Phase 1 — Configuration / auth / proxy contract and container launch

Enable the RESTgym service before building. The evaluated target uses embedded Mongo state, and container restart is the retained reset primitive.

```bash
echo "enabled: true" > apis/person-controller/restgym-api-config.yml

docker rm -f restgym_personcontroller 2>/dev/null || true
docker build -t restgym/personcontroller:latest -f apis/person-controller/Dockerfile .
MSYS_NO_PATHCONV=1 docker run -d --name restgym_personcontroller \
  -p 9090:9090 -p 12345:12345 \
  -e API=person-controller -e TOOL=manual -e RUN=1 \
  restgym/personcontroller:latest
sleep 15
```

### Phase 2 — Trace recording


```text
record_person_full_12.py
```

```bash
python record_person_full_12.py
mkdir -p p2s_traces/person-controller
cp apis/person-controller/specifications/person-controller.yaml p2s_traces/person-controller/personcontroller.yaml

python3 trace_compiler.py \
  --swagger p2s_traces/person-controller/personcontroller.yaml \
  --input p2s_traces/person-controller/primitive_traces.jsonl \
  --output p2s_traces/person-controller/compiled_traces.jsonl \
  --catalog p2s_traces/person-controller/personcontroller_ocli_catalog.json

rm -f personcontroller_p2s_processed_flows.txt personcontroller_p2s_golden_dataset.jsonl personcontroller_p2s_silver_dataset.jsonl
python3 eval_student_p2s_engine.py \
  --target-port 9090 \
  --traces p2s_traces/person-controller/compiled_traces.jsonl \
  --catalog p2s_traces/person-controller/personcontroller_ocli_catalog.json \
  --output-prefix personcontroller_p2s \
  --time-budget 3600
```

### Phase 5 — State reset contract

Reset:

```bash
docker restart restgym_personcontroller
```

---

## 45. Service 10 — `pet-clinic-api`

### Phase 1 — Configuration / auth / proxy contract and container launch

Three Phase-1 details are inseparable: RESTgym must be enabled, the API base path is `/petclinic`, and requests require Basic authentication `admin:admin`. Preserve all three in trace capture, OpenAPI acquisition, and the OCLI profile.

Enable service **before build**:

```bash
echo "enabled: true" > apis/pet-clinic/restgym-api-config.yml
```

Build/run:

```bash
docker rm -f restgym_petclinic 2>/dev/null || true
docker build -t restgym/petclinic:latest -f apis/pet-clinic/Dockerfile .
MSYS_NO_PATHCONV=1 docker run -d --name restgym_petclinic \
  -p 9090:9090 -p 12345:12345 \
  -e API=pet-clinic -e TOOL=manual -e RUN=1 \
  restgym/petclinic:latest
sleep 15
```

PetClinic uses:

```text
context path: /petclinic
Basic auth:   admin:admin
```

Fetch spec:

```bash
mkdir -p p2s_traces/pet-clinic
MSYS_NO_PATHCONV=1 docker exec restgym_petclinic bash -c '
  curl -s -u admin:admin http://localhost:8080/petclinic/v3/api-docs -o /tmp/petclinic.json || \
  curl -s -u admin:admin http://localhost:8080/petclinic/v2/api-docs -o /tmp/petclinic.json
'
MSYS_NO_PATHCONV=1 docker cp restgym_petclinic:/tmp/petclinic.json p2s_traces/pet-clinic/petclinic.json
```

### Phase 2 — Trace recording


```text
record_petclinic_full_35.py
```

```bash
python record_petclinic_full_35.py

python3 trace_compiler.py \
  --swagger p2s_traces/pet-clinic/petclinic.json \
  --input p2s_traces/pet-clinic/primitive_traces.jsonl \
  --output p2s_traces/pet-clinic/compiled_traces.jsonl \
  --catalog p2s_traces/pet-clinic/petclinic_ocli_catalog.json

rm -f petclinic_p2s_processed_flows.txt petclinic_p2s_golden_dataset.jsonl petclinic_p2s_silver_dataset.jsonl
python3 eval_student_p2s_engine.py \
  --target-port 9090 \
  --traces p2s_traces/pet-clinic/compiled_traces.jsonl \
  --catalog p2s_traces/pet-clinic/petclinic_ocli_catalog.json \
  --output-prefix petclinic_p2s \
  --time-budget 3600
```

### Phase 3b — context/auth-correct OCLI profile

The research runner/OCLI profile must use:

```bash
ocli profiles add petclinic_p2s \
  --api-base-url http://localhost:9090/petclinic \
  --openapi-spec "$(pwd)/p2s_traces/pet-clinic/petclinic.json" \
  --api-basic-auth "admin:admin" \
  --command-prefix ""
```

### Phase 5 — State reset contract

Reset:

```bash
docker restart restgym_petclinic
```

---

## 46. Service 11 — `project-tracking-system`

### Phase 1 — Configuration / auth / proxy contract and container launch

Enable the service before building. The target uses in-memory H2 initialized through Flyway; restart is meaningful because it replays the migration/seed lifecycle. Do not replace that with an empty H2 database or a different seed sequence.

```bash
echo "enabled: true" > apis/project-tracking-system/restgym-api-config.yml

docker rm -f restgym_projecttrackingsystem 2>/dev/null || true
docker build -t restgym/project-tracking-system:latest -f apis/project-tracking-system/Dockerfile .
MSYS_NO_PATHCONV=1 docker run -d --name restgym_projecttrackingsystem \
  -p 9090:9090 -p 12345:12345 \
  -e API=project-tracking-system -e TOOL=manual -e RUN=1 \
  restgym/project-tracking-system:latest
sleep 20
```

### Phase 2 — Trace recording


```text
record_pts_full_59.py
```

```bash
python record_pts_full_59.py
mkdir -p p2s_traces/project-tracking-system
cp apis/project-tracking-system/specifications/project-tracking-system.yaml p2s_traces/project-tracking-system/projecttrackingsystem.yaml

python3 trace_compiler.py \
  --swagger p2s_traces/project-tracking-system/projecttrackingsystem.yaml \
  --input p2s_traces/project-tracking-system/primitive_traces.jsonl \
  --output p2s_traces/project-tracking-system/compiled_traces.jsonl \
  --catalog p2s_traces/project-tracking-system/projecttrackingsystem_ocli_catalog.json

rm -f projecttrackingsystem_p2s_processed_flows.txt projecttrackingsystem_p2s_golden_dataset.jsonl projecttrackingsystem_p2s_silver_dataset.jsonl
python3 eval_student_p2s_engine.py \
  --target-port 9090 \
  --traces p2s_traces/project-tracking-system/compiled_traces.jsonl \
  --catalog p2s_traces/project-tracking-system/projecttrackingsystem_ocli_catalog.json \
  --output-prefix projecttrackingsystem_p2s \
  --time-budget 3600
```

### Phase 5 — State reset contract

Reset:

```bash
docker restart restgym_projecttrackingsystem
```

This restarts H2 and replays the Flyway migration/seed lifecycle. Treat that migration/seed replay as part of the reset contract, not an incidental side effect.

---

## 47. Universal Track B Post-Processing and Fidelity Audit

### 47.1 Phase-1 fidelity checklist

Before accepting a run as comparable to the retained Track-B environment, verify the following service-specific invariant:

| Service | Mandatory Phase-1 / runtime invariant |
|---|---|
| `blog` | RESTgym proxy on `9090`; Spring/MySQL launch; SQL reseed reset |
| `erc20` | Dockerfile `/logs` patch before build; `--memory=6g`; mitmproxy dummy-address rewrite; fresh-contract reset |
| `features-service` | `enabled: true` before build so RESTgym/mitmproxy path is active; form-urlencoded constraints |
| `flight-search` | `auth.py` registers ADMIN before build; authenticated proxy path retained; Mongo reseed |
| `gestao-hospital` | session-cookie auto-authentication retained behind RESTgym; Mongo drop/reseed |
| `kafka-rest-proxy` | Kafka/Schema Registry/REST stack ready; topic-level reset |
| `market` | `enabled: true`; session-cookie auth retained; H2 restart reset |
| `notebook-manager` | `enabled: true`; MySQL schema/data SQL re-import reset preserved |
| `person-controller` | `enabled: true`; embedded-Mongo reset by restart |
| `pet-clinic` | `enabled: true`; `/petclinic`; Basic `admin:admin`; matching OCLI profile |
| `project-tracking-system` | `enabled: true`; H2/Flyway migration/seed replay on restart |

### 47.2 Fault post-processing

For every service after the one-hour run:

```bash
python dedup_p2s_goldens.py <service>_p2s_golden_dataset.jsonl
python reclassify_vectors.py <service>_p2s both
```

For strict SBFT Fault Detection, count only `actual_status >= 500` before fault-signature deduplication. Do not include HTTP-200 authorization-bypass Goldens in SBFT FD, although they remain valid P2S security findings under P2S's own taxonomy.

### 47.3 JaCoCo output convention

Normalize the final host-side output to:

```text
results/<service>/code-coverage/coverage.csv
```

or, if the research branch already uses:

```text
results/<service>/code-coverage.csv
```

retain the branch's exact path and document it in the artifact manifest. Do not rename silently after checksums are published.

### 47.4 Final Track B audit targets

The final paper's retained per-service strict FD values are:

| Service | Ops | Strict 5xx FD proxy |
|---|---:|---:|
| blog | 52 | 31 |
| erc20 | 13 | 19 |
| features-service | 18 | 83 |
| flight-search | 40 | 0 |
| gestao-hospital | 20 | 1 |
| kafka-rest-proxy | 50 | 7 |
| market | 13 | 29 |
| notebook-manager | 5 | 25 |
| person-controller | 12 | 58 |
| pet-clinic | 35 | 60 |
| project-tracking-system | 59 | 8 |
| **Total / mean** | **317** | **321 total / 29.18 per API** |

Mean final JaCoCo values:

```text
Branch coverage   14.46%
Line coverage     27.37%
Method coverage   29.07%
```

These are audit targets for comparing the retained artifact, not values that a fresh stochastic rerun must exactly equal. The retained Track-B comparison uses a P2S-native status-aligned FD proxy, trace-derived operation coverage, and final JaCoCo snapshots that may be non-cumulative when a reset restarts the JVM. No Roadrunner/AUC score should be synthesized from endpoint snapshots.

---

# Part VIII — Artifact Layout for Public Releases

## 48. Recommended Public Artifact Structure

Keep the SDK lightweight and publish experiment artifacts separately.

### A. P2S Framework release

```text
p2s-framework/
├── p2s/
├── configs/
├── hooks/
├── docs/
│   ├── P2S_FRAMEWORK_REFERENCE.md
│   └── REPRODUCIBILITY.md
├── SDK_GUIDE.md
├── p2s_colab_train.ipynb        # optional Colab/A100 training reproduction helper
├── README.md
└── pyproject.toml
```

### B. AITasker training artifact

```text
AITasker/
├── backend/
│   ├── primitive_traces.jsonl
│   ├── compiled_traces.jsonl
│   ├── ocli_catalog.json
│   ├── golden_dataset.jsonl
│   ├── silver_dataset.jsonl
│   ├── final_training_dataset.jsonl
│   └── ...
├── ai-service/
└── reproduction/
    ├── historical training logs / notebook copy if retained
    ├── environment notes
    └── checksums
```

The **public convenience copy of the Colab training notebook lives at the root of the P2S framework repository**. This location does not make it part of the installed SDK; it is kept there so a reproducer can go directly from `final_training_dataset.jsonl` to the paper's Qwen3.5-9B training procedure without navigating a separate experiment repository.

### C. Track A SEAL artifact

```text
SWP391_SealHackathon_BackEnd/
├── primitive_traces.jsonl
├── compiled_traces.jsonl
├── seal_ocli_catalog.json
├── <p2s fine-tuned JSONL artifacts>
├── <base-qwen JSONL artifacts>
├── <deepseek JSONL artifacts>
├── cats_report/
├── .schemathesis/ or Schemathesis reports
└── reproduction/
```

### D. AutoRestTest artifact

```text
autoresttest/
├── configurations.toml
├── seal_openapi.json
├── data/seal_openapi/
└── reproduction/
```

### E. Track B RESTgym artifact

```text
restgym/
├── p2s_traces/<service>/...
├── <service>_p2s_golden_dataset.jsonl
├── <service>_p2s_silver_dataset.jsonl
├── <service>_p2s_run_metadata.json
├── results/<service>/code-coverage.csv
└── reproduction/
    ├── record_blog_full_52.py
    ├── record_erc20_full_13.py
    ├── record_features_full_18.py
    ├── record_flightsearch_full_40.py
    ├── record_gestao_full_20.py
    ├── record_kafkarest_full_50.py
    ├── record_market_full_13.py
    ├── record_notebookmanager_full_5.py
    ├── record_person_full_12.py
    ├── record_petclinic_full_35.py
    ├── record_pts_full_59.py
    ├── trace_compiler.py
    ├── eval_student_p2s_engine.py
    ├── dedup_p2s_goldens.py
    └── reclassify_vectors.py
```

---

# Part IX — Expanding P2S to a New System

## 49. Minimal Porting Contract

To port P2S to another API, you need only five pieces of target knowledge:

1. **Target URL and OpenAPI document**
2. **A valid stateful workflow** (manual UI activity, curl scripts, integration tests, etc.)
3. **Flow-boundary strategy**
4. **Authentication/OCLI profile setup**
5. **State reset adapter**

The core mutation taxonomy and execution-verification loop should not be rewritten.

---

## 50. New-Target Procedure

### Step 1 — create target config

```toml
[target]
name = "my_api"
base_url = "http://localhost:8080/api"
openapi_spec = "openapi.json"
state_adapter = "postgres"     # or wire a custom adapter
executor_adapter = "ocli"
golden_out = "my_api_golden_dataset.jsonl"
silver_out = "my_api_silver_dataset.jsonl"
checkpoint_file = "my_api_processed_flows.txt"

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

### Step 2 — collect at least one successful workflow

```bash
p2s proxy --config configs/my_api.toml
```

Drive the API through its real workflow. The traffic source can be automated scripts or ordinary user interaction through the UI.

### Step 3 — compile

```bash
p2s compile --config configs/my_api.toml
```

### Step 4 — evaluate

```bash
p2s fuzz --config configs/my_api.toml
```

### Step 5 — analyze

```bash
p2s reclassify --backend my_api --slm-url http://localhost:1234/v1
p2s m1 --backend my_api
p2s analyze --dir .
```

### Step 6 — if the target has unusual state

Implement target-specific state restoration without changing the security reasoning core. Track B demonstrates several examples:

```text
SQL reseed
Docker restart
Mongo drop + reseed
blockchain contract redeployment
Kafka topic deletion/recreation
PostgreSQL template snapshots
```

That separation is the practical meaning of P2S being expandable across unrelated systems.

---

# Part X — Reproducibility Checklist

## 51. Before Running

- [ ] Record repository URL and exact commit SHA.
- [ ] Record branch name.
- [ ] Record Python / Java / Node / Docker versions.
- [ ] Record P2S wheel version and checksum.
- [ ] Record exact Hugging Face model revision/commit.
- [ ] Record llama.cpp commit/build.
- [ ] Confirm the target is isolated and authorized.
- [ ] Use non-production accounts and secrets.
- [ ] Fetch a fresh OpenAPI document where required.
- [ ] Clear stale checkpoints before a fresh repetition.

## 52. During Running

- [ ] Preserve raw primitive traces.
- [ ] Preserve compiled traces and OCLI catalog.
- [ ] Preserve execution log.
- [ ] Preserve Golden/Silver JSONL without manual editing.
- [ ] Preserve run metadata.
- [ ] Record wall-clock start/end times.
- [ ] Record model endpoint/model identifier.
- [ ] Record target reset behavior.

## 53. After Running

- [ ] Run false-positive verification for Track A.
- [ ] Deduplicate faults with a documented signature rule.
- [ ] Keep candidate counts distinct from verified counts.
- [ ] Keep P2S security-bypass Goldens distinct from SBFT 5xx-only FD.
- [ ] Preserve JaCoCo raw/CSV outputs.
- [ ] Do not manufacture AUC without metric-time-series data.
- [ ] Compute SHA-256 checksums for published JSONL/CSV/model-reference manifests.
- [ ] Publish a machine-readable environment manifest.

---

# 54. Final Reproduction Graph

```text
                                      ┌──────────────────────────┐
                                      │  P2S Framework v1.1.0   │
                                      │ proxy/compiler/engine    │
                                      └────────────┬─────────────┘
                                                   │
                    ┌──────────────────────────────┼──────────────────────────────┐
                    │                              │                              │
                    ▼                              ▼                              ▼
          AITasker training                Track A: SEAL                  Track B: RESTgym
          branch feat/hung/...             branch be-10/07               11 services
                    │                              │                              │
         capture + compile                  capture + compile              per-service trace
                    │                              │                              │
        base Qwen self-play                 P2S/Base/DeepSeek             P2S fine-tuned Q8_0
                    │                              │                              │
        Golden/Silver corpus                verified TP audit             1 h per service
                    │                              │                              │
        final SFT dataset          ┌───────────────┴──────────────┐       JaCoCo + 5xx FD
                    │              │                              │
             LoRA fine-tune  AutoRestTest                  CATS/Schemathesis
                    │        independent baseline           independent baselines
                    ▼
             Hugging Face
      LoRA / 4-bit / 16-bit / GGUF
                    │
                    └──────────> llama.cpp :8081 ────────────────┘
```

This organization keeps the **reusable method**, **training source**, **model artifacts**, **independent semantic evaluation**, **conventional baselines**, and **standardized benchmark** independently inspectable while still giving a complete end-to-end reproduction path for the research.
