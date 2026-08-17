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

# Part IV — Operation 2: Track A P2S Evaluation on SEAL

## 17. Clone the SEAL Evaluation Branch

```bash
git clone https://github.com/triet2809/SWP391_SealHackathon_BackEnd.git
cd SWP391_SealHackathon_BackEnd
git switch be-10/07
```

The retained Track A target is a Spring Boot / Java 17 backend using PostgreSQL and a base URL of:

```text
http://localhost:8080/api
```

---

## 18. Initialize the SEAL Database

Use the exact SQL filenames retained in the SEAL research branch:

```bash
psql "postgresql://postgres:postgres@localhost:5432/postgres" \
  -c "DROP DATABASE IF EXISTS seal_hackathon;"

psql "postgresql://postgres:postgres@localhost:5432/postgres" \
  -c "CREATE DATABASE seal_hackathon;"

psql "postgresql://postgres:postgres@localhost:5432/seal_hackathon" \
  -f seal_hackathon_full_2026-07-04.sql

psql "postgresql://postgres:postgres@localhost:5432/seal_hackathon" <<'SQL'
\i migration_gapfill.sql
\i migration_gapfill2.sql
\i migration_gapfill3.sql
SQL
```

---

## 19. Build and Launch SEAL

```bash
mvn clean package -DskipTests

java -jar target/seal-hackathon-backend-0.0.1-SNAPSHOT.jar \
  --spring.datasource.url=jdbc:postgresql://localhost:5432/seal_hackathon \
  --spring.datasource.username=postgres \
  --spring.datasource.password=postgres \
  --app.security.jwt.secret="${SEAL_JWT_SECRET}"
```

Use a test-only signing secret via environment variable. Do not publish a real production secret.

Verify:

```bash
curl http://localhost:8080/api/v3/api-docs -o seal_openapi.json
```

---

## 20. Record the 21 SEAL Business Flows

The final SEAL proxy uses explicit `X-Flow-ID` tags because the flow suite shares authenticated sessions instead of resetting on every login/register operation.

### Historical parity

Terminal A:

```bash
TARGET_PORT=8080 python3 proxy.py
```

Terminal B:

```bash
BASE_URL=http://localhost:8090/api \
  bash seal-simulations/seal-flows/seal_flows.sh
```

### Framework-native

Use `configs/seal_hackathon.toml` or a copy with the exact local paths:

```bash
p2s proxy --config configs/seal_hackathon.toml
```

The proxy should:

- listen on `8090`;
- forward to `http://localhost:8080`;
- use header-tagged flows;
- skip health checks;
- mask Authorization/Cookie/signature values in persisted traces.

---

## 21. Compile the SEAL Trace

Register OCLI:

```bash
ocli profiles add seal \
  --api-base-url http://localhost:8080/api \
  --openapi-spec http://localhost:8080/api/v3/api-docs \
  --api-bearer-token "" \
  --command-prefix ""

ocli use seal
```

Historical compiler:

```bash
python3 trace_compiler.py
```

Framework compiler:

```bash
p2s compile --config configs/seal_hackathon.toml
```

The SEAL compiler must strip the Spring `/api` context path for OpenAPI route matching and skip malformed paths containing an empty path parameter segment.

Expected:

```text
primitive_traces.jsonl
compiled_traces.jsonl
seal_ocli_catalog.json / ocli_catalog.json
```

---

## 22. Run the Fine-Tuned P2S Specialist

First serve Q8_0 at `http://localhost:8081/v1` as shown in Sections 5–7.

Use a SEAL config:

```toml
[target]
name = "seal_hackathon"
base_url = "http://localhost:8080/api"
openapi_spec = "seal_openapi.json"
state_adapter = "postgres"
executor_adapter = "ocli"
golden_out = "llamacpp_golden_dataset.jsonl"
silver_out = "llamacpp_silver_dataset.jsonl"
checkpoint_file = "llamacpp_processed_flows.txt"

[postgres]
active_db = "seal_hackathon"
template_db = "seal_hackathon_snap"
admin_url = "postgresql://postgres:postgres@localhost:5432/postgres"
seed_command = "psql -U postgres -d seal_hackathon -f seal_hackathon_full_2026-07-04.sql"
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

Then:

```bash
p2s fuzz --config configs/seal_hackathon.toml
```

### Exact archived Track A parity

The final SEAL branch also retains the audit-fixed evaluator that was actually used to generate the paper artifacts:

```bash
python eval_student_p2s_engine.py
```

For exact historical-result reproduction, prefer the retained research runner because it preserves the final experiment's runtime patches, response parser, output prefixes, and post-hoc join conventions. The framework command is the normalized SDK path for new targets and new repetitions.

---

## 23. Run the Base-Qwen and DeepSeek Track A Controls

The SEAL evaluator supports switchable inference backends. Keep the **same traces, target state, catalog, taxonomy, execution path, and max attempts**; change only the model backend.

### Base Qwen3.5-9B

Serve the untuned Qwen3.5-9B at an OpenAI-compatible endpoint such as LM Studio, then set:

```python
INFERENCE_BACKEND = "lm_studio"
```

or provide an equivalent P2S TOML pointing `base_url` to the base model server.

### DeepSeek-V4-Flash

Set the provider endpoint/key using environment variables; never commit keys:

```bash
export DEEPSEEK_API_KEY="<your-key>"
```

Then configure the evaluator/P2S OpenAI-compatible adapter for the DeepSeek endpoint and model name.

Run each backend into a separate output prefix so results cannot collide.

---

## 24. Track A Post-Hoc Verification

The critical distinction in Track A is **candidate Golden vs. post-hoc verified true positive**.

Framework commands:

```bash
p2s reclassify \
  --backend llamacpp \
  --slm-url http://localhost:1234/v1

p2s m1 --backend llamacpp

p2s verify \
  --golden-file llamacpp_golden_dataset_reclassified.jsonl \
  --verified-out seal_p2s_verified_goldens.jsonl

p2s analyze --dir .
```

Historical SEAL scripts, if reproducing the retained branch exactly:

```bash
python validate_seal_goldens.py \
  --golden-file llamacpp_golden_dataset.jsonl \
  --output-verified llamacpp_verified_goldens.jsonl

python deduplicate_goldens.py llamacpp_verified_goldens.jsonl
python reclassify_vectors.py llamacpp both
```

The verifier must filter at least:

- CLI help bleed (`--help` / `-h`);
- Jackson-ignored pseudo mass-assignment parameters;
- ordinary authorized `200/201` responses where no identity/resource mutation occurred.

For comparison against the paper, the retained final Track A table is:

| Metric | P2S fine-tuned | DeepSeek | Base Qwen |
|---|---:|---:|---:|
| Executed records | 1,075 | 1,094 | 1,122 |
| Candidate Goldens | 48 | 29 | 21 |
| Verified true positives | **31** | 26 | 16 |
| Unique verified signatures | **30** | 26 | 16 |
| Verified kill rate | **2.9%** | 2.4% | 1.4% |

Do not force reruns to match these counts; record seeds/model revisions/runtime versions and report observed results.

---

# Part V — Operation 3: AutoRestTest Track A Baseline

## 25. Purpose

AutoRestTest is an independent baseline. It does **not** use the P2S fine-tuned model or the P2S mutation engine. It is included here because full P2S-paper reproducibility requires reproducing the baseline evidence against the same SEAL target.

Use the same running SEAL backend, sanitized OpenAPI source, and a fresh Coordinator JWT.

---

## 26. Clone AutoRestTest

```bash
git clone https://github.com/selab-gatech/autoresttest.git
cd autoresttest
```

Create the compatibility environment used by the archived run:

```bash
python -m venv venv
source venv/Scripts/activate
python -m pip install --upgrade pip setuptools wheel

# Historical Windows/Python-3.12 compatibility patches used in the run:
sed -i 's/<3.11/<3.13/g' pyproject.toml
sed -i 's/==/>=/g' requirements.txt
sed -i '/^python>=/d; /^pip>=/d; /^setuptools>=/d; /^wheel>=/d' requirements.txt

pip install -r requirements.txt
pip install -e . --no-deps
export PYTHONPATH="$(pwd)/src"
```

If upstream AutoRestTest has since become Python-3.12 compatible, preserve the commit/revision used for your reproduction and avoid unnecessary patches.

---

## 27. Prepare the Shared SEAL Contract

Fetch a fresh OpenAPI spec:

```bash
curl -s http://localhost:8080/api/v3/api-docs -o seal_openapi.json
```

Sanitize it exactly for baseline stability:

```bash
python - <<'PY'
import json
p = "seal_openapi.json"
with open(p, encoding="utf-8") as f:
    spec = json.load(f)

spec["servers"] = [{"url": "http://localhost:8080/api"}]
paths = spec.get("paths", {})
paths.pop("/auth/logout", None)
if "/users/{id}" in paths:
    paths["/users/{id}"].pop("delete", None)
if "/users/me" in paths:
    paths["/users/me"].pop("delete", None)

with open(p, "w", encoding="utf-8") as f:
    json.dump(spec, f, indent=2)
PY
```

Fetch a fresh Coordinator token after clearing stale revocations:

```bash
python - <<'PY'
import json, psycopg2, urllib.request

conn = psycopg2.connect("postgresql://postgres:postgres@localhost:5432/seal_hackathon")
conn.autocommit = True
with conn.cursor() as cur:
    cur.execute("TRUNCATE revoked_tokens;")
conn.close()

req = urllib.request.Request(
    "http://localhost:8080/api/auth/login",
    data=json.dumps({"email":"coordinator@seal.eval","password":"Eval@1234567"}).encode(),
    headers={"Content-Type":"application/json"},
)
with urllib.request.urlopen(req) as r:
    token = json.loads(r.read().decode())["accessToken"]
with open("seal_coordinator_jwt.txt", "w") as f:
    f.write(token)
print("token saved")
PY
```

---

## 28. AutoRestTest Configuration

The final reported run used:

```text
spec                  seal_openapi.json
strict_validation     false
Header Agent          disabled
cached graph           false
cached table           false
request duration       18,000 seconds (5 h)
Windows dispatcher     15 ms throttle
Authorization          fresh long-lived Coordinator Bearer JWT
LLM in completed run   DeepSeek-V4-Flash
```

**Archival note:** the old setup text contains a local base-Qwen model template. Do not use that template if the goal is to reproduce the completed paper run.

Generate `configurations.toml` using your own provider credentials via environment variables. Never embed an API key into the repository.

The important experiment controls are:

```toml
[spec]
location = "seal_openapi.json"
recursion_limit = 1
strict_validation = false

[agent]
max_combinations = 12
max_total_combinations = 3000
base_samples_per_size = 200
combination_seed = 42

[agent.value]
parallelize = true
max_workers = 2

[agents.header]
enabled = false

[cache]
use_cached_graph = false
use_cached_table = false

[q_learning]
learning_rate = 0.1
discount_factor = 0.9
max_exploration = 1.0

[request_generation]
time_duration = 18000
mutation_rate = 0.2

[api]
override_url = false
host = "localhost"
port = 8080
```

Add the provider/model fields exactly as required by the AutoRestTest revision you publish, with DeepSeek-V4-Flash as the value-model configuration for final-run parity.

---

## 29. Windows Socket-Safety Patch

The retained Windows run inserted a 15 ms dispatcher delay to avoid ephemeral-port exhaustion:

```text
time.sleep(0.015)
```

The historical file is:

```text
src/autoresttest/utils/utils.py
```

If your published AutoRestTest artifact contains the patched file, use that exact version rather than applying a blind text replacement to a newer upstream revision.

---

## 30. Execute AutoRestTest

```bash
python -m autoresttest.autoresttest --skip-wizard
```

The target budget is **18,000 seconds**.

Retain the complete generated directory:

```text
data/seal_openapi/
```

In particular, preserve:

```text
data/seal_openapi/server_errors.json
```

plus graph/Q-table/config/run logs produced by the specific AutoRestTest revision.

The native counters are evidence from AutoRestTest; they are **not automatically equivalent to verified security vulnerabilities**. Preserve both native counts and post-hoc semantic audit outputs.

---

# Part VI — Operation 4: CATS and Schemathesis Track A Baselines

## 31. Shared Inputs

CATS and Schemathesis use the same:

```text
seal_openapi.json
fresh Coordinator JWT
http://localhost:8080/api
```

The sanitized contract should remove `/auth/logout` and self-deletion operations, exactly as in the AutoRestTest setup.

---

## 32. CATS

### Download

The historical Windows procedure downloaded the latest Endava CATS Windows release and extracted `cats.exe`. For strict reproducibility, publish or record the exact CATS version/commit used rather than relying on `latest` indefinitely.

### Token

If reusing the token-generation step above:

```bash
cp seal_coordinator_jwt.txt cats_jwt.txt
```

### Run

```bash
COORD_TOKEN=$(cat cats_jwt.txt)

./cats.exe \
  --contract seal_openapi.json \
  --server http://localhost:8080/api \
  -H "Authorization=Bearer ${COORD_TOKEN}" \
  --output cats_report
```

Preserve the complete output directory:

```text
cats_report/
```

The post-hoc audit should inspect individual JSON test artifacts, not only the dashboard total.

---

## 33. Schemathesis

Install:

```bash
source venv/Scripts/activate
pip install "schemathesis[all]"
```

Run:

```bash
COORD_TOKEN=$(cat cats_jwt.txt)

schemathesis run seal_openapi.json \
  --url http://localhost:8080/api \
  -H "Authorization: Bearer ${COORD_TOKEN}" \
  --checks all \
  --max-examples 100 \
  --report-junit-path schemathesis_report.xml \
  --report-vcr-path schemathesis_vcr.yaml
```

Preserve:

```text
schemathesis_report.xml
schemathesis_vcr.yaml
.schemathesis/        # when created by the installed version
```

Track A interpretation must keep raw server failures separate from verified deep/stateful security outcomes.

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

## 35. Track B Exact Experimental Shape

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

### Build and launch

```bash
docker build -t restgym/blog:latest -f apis/blog/Dockerfile .
docker rm -f restgym_blog 2>/dev/null || true

MSYS_NO_PATHCONV=1 docker run -d --name restgym_blog \
  -p 9090:9090 -p 12345:12345 \
  -e API=blog -e TOOL=manual -e RUN=1 \
  restgym/blog:latest
sleep 15
```

### Trace recorder

```text
import json
import os
import requests

PROXY_URL = "http://localhost:9090"
OUT_FILE = "p2s_traces/blog/primitive_traces.jsonl"
os.makedirs("p2s_traces/blog", exist_ok=True)

steps = []
step_cnt = 1

def record(method, path, params=None, json_body=None, flow_id="flow_blog_full"):
    global step_cnt
    url = f"{PROXY_URL}{path}"
    headers = {"Content-Type": "application/json"}

    try:
        if method == "GET": res = requests.get(url, headers=headers, params=params, timeout=10)
        elif method == "POST": res = requests.post(url, headers=headers, params=params, json=json_body, timeout=10)
        elif method == "PUT": res = requests.put(url, headers=headers, params=params, json=json_body, timeout=10)
        elif method == "DELETE": res = requests.delete(url, headers=headers, params=params, timeout=10)

        try: res_data = res.json()
        except: res_data = res.text

        full_path_str = path
        if params:
            qp = "&".join([f"{k}={v}" for k, v in params.items()])
            full_path_str += f"?{qp}"

        trace_step = {
            "flow_id": flow_id,
            "step": step_cnt,
            "request": {
                "method": method,
                "path": full_path_str,
                "headers": headers,
                "body": json_body
            },
            "response": {
                "status_code": res.status_code,
                "body": res_data
            }
        }
        steps.append(trace_step)
        print(f"  [{step_cnt:>2}/52] {method:6} {full_path_str[:50]:<50} -> {res.status_code}")
        step_cnt += 1
        return res_data
    except Exception as e:
        print(f"  [{step_cnt:>2}/52] ERROR {method} {path}: {e}")
        step_cnt += 1
        return {}

print("=== 1. Resetting MySQL Database inside Container ===")
os.system("docker exec restgym_blog mysql -ublog -pblog blogapi < apis/blog/database/blogapi.sql")

print("\n=== 2. Recording ALL 52 Endpoints Trace Across 4 Flows ===")

# ── FLOW 1: User & Auth Endpoints (12 ops) ──
record("GET", "/api/users/checkUsernameAvailability", params={"username": "userusername"}, flow_id="flow_users")
record("GET", "/api/users/checkEmailAvailability", params={"email": "user@gmail.com"}, flow_id="flow_users")
me = record("GET", "/api/users/me", flow_id="flow_users")
uname = me.get("username", "userusername") if isinstance(me, dict) else "userusername"

record("POST", "/api/users", json_body={"username":"newuser","password":"password123","email":"new@gmail.com","firstName":"New","lastName":"User"}, flow_id="flow_users")
record("PUT", "/api/users/setOrUpdateInfo", json_body={"firstName":"UpdatedFirst","lastName":"UpdatedLast"}, flow_id="flow_users")
record("PUT", f"/api/users/{uname}", json_body={"firstName":"UserFirst","lastName":"UserLast","email":"user@gmail.com"}, flow_id="flow_users")
record("GET", f"/api/users/{uname}/profile", flow_id="flow_users")
record("GET", f"/api/users/{uname}/posts", flow_id="flow_users")
record("GET", f"/api/users/{uname}/albums", flow_id="flow_users")
record("PUT", f"/api/users/{uname}/giveAdmin", flow_id="flow_users")
record("PUT", f"/api/users/{uname}/takeAdmin", flow_id="flow_users")
record("DELETE", f"/api/users/newuser", flow_id="flow_users")

# ── FLOW 2: Categories, Tags, Posts & Comments (22 ops) ──
record("GET", "/api/categories", params={"page":0,"size":10}, flow_id="flow_content")
c1 = record("POST", "/api/categories", json_body={"name":"Technology"}, flow_id="flow_content")
cid = c1.get("id", 1) if isinstance(c1, dict) else 1
record("GET", f"/api/categories/{cid}", flow_id="flow_content")
record("PUT", f"/api/categories/{cid}", json_body={"name":"Tech & AI"}, flow_id="flow_content")

record("GET", "/api/tags", params={"page":0,"size":10}, flow_id="flow_content")
t1 = record("POST", "/api/tags", json_body={"name":"AI"}, flow_id="flow_content")
tid = t1.get("id", 1) if isinstance(t1, dict) else 1
record("GET", f"/api/tags/{tid}", flow_id="flow_content")
record("PUT", f"/api/tags/{tid}", json_body={"name":"Artificial Intelligence"}, flow_id="flow_content")

record("GET", "/api/posts", params={"page":0,"size":10}, flow_id="flow_content")
p1 = record("POST", "/api/posts", json_body={"title":"AI Fuzzing","body":"P2S testing blog api","categoryId":cid,"tags":["AI"]}, flow_id="flow_content")
pid = p1.get("id", 1) if isinstance(p1, dict) else 1
record("GET", f"/api/posts/{pid}", flow_id="flow_content")
record("GET", f"/api/posts/category/{cid}", params={"page":0,"size":10}, flow_id="flow_content")
record("GET", f"/api/posts/tag/{tid}", params={"page":0,"size":10}, flow_id="flow_content")
record("PUT", f"/api/posts/{pid}", json_body={"title":"Updated AI Fuzzing","body":"Updated content","categoryId":cid,"tags":["AI"]}, flow_id="flow_content")

record("GET", f"/api/posts/{pid}/comments", params={"page":0,"size":10}, flow_id="flow_content")
cm1 = record("POST", f"/api/posts/{pid}/comments", json_body={"body":"Great post!"}, flow_id="flow_content")
cmid = cm1.get("id", 1) if isinstance(cm1, dict) else 1
record("GET", f"/api/posts/{pid}/comments/{cmid}", flow_id="flow_content")
record("PUT", f"/api/posts/{pid}/comments/{cmid}", json_body={"body":"Updated comment!"}, flow_id="flow_content")
record("DELETE", f"/api/posts/{pid}/comments/{cmid}", flow_id="flow_content")

record("DELETE", f"/api/categories/{cid}", flow_id="flow_content")
record("DELETE", f"/api/tags/{tid}", flow_id="flow_content")
record("DELETE", f"/api/posts/{pid}", flow_id="flow_content")

# ── FLOW 3: Albums & Photos (11 ops) ──
record("GET", "/api/albums", params={"page":0,"size":10}, flow_id="flow_media")
a1 = record("POST", "/api/albums", json_body={"title":"My Tech Album","photo":"cover.jpg"}, flow_id="flow_media")
aid = a1.get("id", 1) if isinstance(a1, dict) else 1
record("GET", f"/api/albums/{aid}", flow_id="flow_media")
record("PUT", f"/api/albums/{aid}", json_body={"title":"Updated Tech Album","photo":"cover2.jpg"}, flow_id="flow_media")
record("GET", f"/api/albums/{aid}/photos", params={"page":0,"size":10}, flow_id="flow_media")

record("GET", "/api/photos", params={"page":0,"size":10}, flow_id="flow_media")
ph1 = record("POST", "/api/photos", json_body={"albumId":aid,"title":"Diagram","url":"http://img.com/1.png","thumbnailUrl":"http://img.com/1_thumb.png"}, flow_id="flow_media")
phid = ph1.get("id", 1) if isinstance(ph1, dict) else 1
record("GET", f"/api/photos/{phid}", flow_id="flow_media")
record("PUT", f"/api/photos/{phid}", json_body={"albumId":aid,"title":"Updated Diagram","url":"http://img.com/2.png","thumbnailUrl":"http://img.com/2_thumb.png"}, flow_id="flow_media")
record("DELETE", f"/api/photos/{phid}", flow_id="flow_media")
record("DELETE", f"/api/albums/{aid}", flow_id="flow_media")

# ── FLOW 4: Todos (7 ops) ──
record("GET", "/api/todos", params={"page":0,"size":10}, flow_id="flow_todos")
td1 = record("POST", "/api/todos", json_body={"title":"Finish P2S Eval","completed":False}, flow_id="flow_todos")
tdid = td1.get("id", 1) if isinstance(td1, dict) else 1
record("GET", f"/api/todos/{tdid}", flow_id="flow_todos")
record("PUT", f"/api/todos/{tdid}", json_body={"title":"Finish P2S Eval Updated","completed":False}, flow_id="flow_todos")
record("PUT", f"/api/todos/{tdid}/complete", json_body={}, flow_id="flow_todos")
record("PUT", f"/api/todos/{tdid}/unComplete", json_body={}, flow_id="flow_todos")
record("DELETE", f"/api/todos/{tdid}", flow_id="flow_todos")

with open(OUT_FILE, "w", encoding="utf-8") as f:
    for s in steps:
        f.write(json.dumps(s, ensure_ascii=False) + "\n")

print(f"\n[SUCCESS] Recorded ALL {len(steps)} operations across 4 execution flows directly to {OUT_FILE}!")
```

Run:

```bash
python record_blog_full_52.py
```

Expected trace:

```text
p2s_traces/blog/primitive_traces.jsonl
```

Compile:

```bash
python3 trace_compiler.py \
  --swagger apis/blog/specifications/blog.yaml \
  --input p2s_traces/blog/primitive_traces.jsonl \
  --output p2s_traces/blog/compiled_traces.jsonl \
  --catalog p2s_traces/blog/blog_ocli_catalog.json
```

Evaluate:

```bash
rm -f blog_p2s_golden_dataset.jsonl blog_p2s_silver_dataset.jsonl blog_p2s_processed_flows.txt

python3 eval_student_p2s_engine.py \
  --target-port 9090 \
  --traces p2s_traces/blog/compiled_traces.jsonl \
  --catalog p2s_traces/blog/blog_ocli_catalog.json \
  --output-prefix blog_p2s \
  --time-budget 3600
```

State reset used by the runner:

```bash
docker exec restgym_blog mysql -ublog -pblog blogapi < apis/blog/database/blogapi.sql
```

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

Recorder:

```text
import json
import os
import requests

PROXY_URL = "http://localhost:9090"
OUT_FILE = "p2s_traces/erc20/primitive_traces.jsonl"
os.makedirs("p2s_traces/erc20", exist_ok=True)

DUMMY_ADDR = "0x0000000000000000000000000000000000000000"
OWNER_ADDR = "0x90F8bf6A479f320ead074411a4B0e7944Ea8c9C1"
SPENDER_ADDR = "0xFFcf8FDEE72ac11b5c542428B35EEF5769C409f0"

steps = []
step_cnt = 1

def record(method, path, params=None, json_body=None, flow_id="flow_erc20_full"):
    global step_cnt
    url = f"{PROXY_URL}{path}"
    headers = {"Content-Type": "application/json"}

    try:
        if method == "GET": res = requests.get(url, headers=headers, params=params, timeout=10)
        elif method == "POST": res = requests.post(url, headers=headers, params=params, json=json_body, timeout=10)

        try: res_data = res.json()
        except: res_data = res.text

        full_path_str = path
        if params:
            qp = "&".join([f"{k}={v}" for k, v in params.items()])
            full_path_str += f"?{qp}"

        trace_step = {
            "flow_id": flow_id,
            "step": step_cnt,
            "request": {"method": method, "path": full_path_str, "headers": headers, "body": json_body},
            "response": {"status_code": res.status_code, "body": res_data}
        }
        steps.append(trace_step)
        print(f"  [{step_cnt:>2}/13] {method:6} {full_path_str[:50]:<50} -> {res.status_code}")
        step_cnt += 1
        return res_data
    except Exception as e:
        print(f"  [{step_cnt:>2}/13] ERROR {method} {path}: {e}")
        step_cnt += 1
        return {}

print("=== 1. Deploying Fresh ERC-20 Contract ===")
os.system("docker exec restgym_erc20 python3 /api/init-contract.py")

print("\n=== 2. Recording ALL 13 Operations for ERC-20 Token Lifecycle ===")

# 1. Config & Metadata (6 ops)
record("GET", "/config", flow_id="flow_erc20")
record("POST", "/deploy", json_body={"initialAmount": 1000000, "tokenName": "TestToken", "decimalUnits": 18, "tokenSymbol": "TST"}, flow_id="flow_erc20")
record("GET", f"/{DUMMY_ADDR}/name", flow_id="flow_erc20")
record("GET", f"/{DUMMY_ADDR}/symbol", flow_id="flow_erc20")
record("GET", f"/{DUMMY_ADDR}/decimals", flow_id="flow_erc20")
record("GET", f"/{DUMMY_ADDR}/totalSupply", flow_id="flow_erc20")
record("GET", f"/{DUMMY_ADDR}/version", flow_id="flow_erc20")

# 2. Balance & Approvals (3 ops)
record("GET", f"/{DUMMY_ADDR}/balanceOf/{OWNER_ADDR}", flow_id="flow_erc20")
record("POST", f"/{DUMMY_ADDR}/approve", json_body={"spender": SPENDER_ADDR, "value": 1000}, flow_id="flow_erc20")
record("GET", f"/{DUMMY_ADDR}/allowance", params={"ownerAddress": OWNER_ADDR, "spenderAddress": SPENDER_ADDR}, flow_id="flow_erc20")

# 3. ApproveAndCall, Transfer & TransferFrom (3 ops)
record("POST", f"/{DUMMY_ADDR}/approveAndCall", json_body={"spender": SPENDER_ADDR, "value": 500, "extraData": "0x00"}, flow_id="flow_erc20")
record("POST", f"/{DUMMY_ADDR}/transfer", json_body={"to": SPENDER_ADDR, "value": 250}, flow_id="flow_erc20")
record("POST", f"/{DUMMY_ADDR}/transferFrom", json_body={"from": OWNER_ADDR, "to": SPENDER_ADDR, "value": 100}, flow_id="flow_erc20")

with open(OUT_FILE, "w", encoding="utf-8") as f:
    for s in steps: f.write(json.dumps(s, ensure_ascii=False) + "\n")

print(f"\n[SUCCESS] Recorded ALL {len(steps)} operations directly to {OUT_FILE}!")

```

```bash
python record_erc20_full_13.py
```

Compile:

```bash
python3 trace_compiler.py \
  --swagger apis/erc20/specifications/erc20.yaml \
  --input p2s_traces/erc20/primitive_traces.jsonl \
  --output p2s_traces/erc20/compiled_traces.jsonl \
  --catalog p2s_traces/erc20/erc20_ocli_catalog.json
```

Evaluate:

```bash
rm -f erc20_p2s_golden_dataset.jsonl erc20_p2s_silver_dataset.jsonl erc20_p2s_processed_flows.txt
python3 eval_student_p2s_engine.py \
  --target-port 9090 \
  --traces p2s_traces/erc20/compiled_traces.jsonl \
  --catalog p2s_traces/erc20/erc20_ocli_catalog.json \
  --output-prefix erc20_p2s \
  --time-budget 3600
```

Fast state reset:

```bash
docker exec restgym_erc20 python3 /api/init-contract.py
```

The RESTgym proxy rewrites the dummy contract address to the newly deployed contract.

For coverage, extract only `BOOT-INF/classes` from the application JAR to avoid duplicate third-party/Lombok classes before running JaCoCo report generation.

---

## 38. Service 3 — `features-service`

Enable the service:

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

Recorder:

```text
import json
import os
import requests
import time

PROXY_URL = "http://localhost:9090"
OUT_FILE = "p2s_traces/features-service/primitive_traces.jsonl"
os.makedirs("p2s_traces/features-service", exist_ok=True)

steps = []
step_cnt = 1

def record(method, path, params=None, json_body=None, form_data=None, flow_id="flow_features_full"):
    global step_cnt
    url = f"{PROXY_URL}{path}"
    headers = {}

    try:
        if method == "GET":
            res = requests.get(url, headers=headers, params=params, timeout=10)
        elif method == "POST":
            if form_data:
                headers["Content-Type"] = "application/x-www-form-urlencoded"
                res = requests.post(url, headers=headers, data=form_data, timeout=10)
            else:
                headers["Content-Type"] = "application/json"
                res = requests.post(url, headers=headers, json=json_body, timeout=10)
        elif method == "PUT":
            if form_data:
                headers["Content-Type"] = "application/x-www-form-urlencoded"
                res = requests.put(url, headers=headers, data=form_data, timeout=10)
            else:
                headers["Content-Type"] = "application/json"
                res = requests.put(url, headers=headers, json=json_body, timeout=10)
        elif method == "DELETE":
            res = requests.delete(url, headers=headers, timeout=10)

        try: res_data = res.json()
        except: res_data = res.text

        trace_step = {
            "flow_id": flow_id,
            "step": step_cnt,
            "request": {"method": method, "path": path, "headers": headers, "body": json_body or form_data},
            "response": {"status_code": res.status_code, "body": res_data}
        }
        steps.append(trace_step)
        print(f"  [{step_cnt:>2}/18] {method:6} {path:<45} -> {res.status_code}")
        step_cnt += 1
        return res_data
    except Exception as e:
        print(f"  [{step_cnt:>2}/18] ERROR {method} {path}: {e}")
        step_cnt += 1
        return {}

print("=== 1. Resetting H2 Database & Waiting 10s for Tomcat ===")
os.system("docker restart restgym_features_service")
time.sleep(10)

print("\n=== 2. Recording ALL 18 Operations for Features Service ===")

# 1. Product Lifecycle (3 ops)
record("GET", "/products", flow_id="flow_features")
record("POST", "/products/SMARTPHONE", flow_id="flow_features")
record("GET", "/products/SMARTPHONE", flow_id="flow_features")

# 2. Features Lifecycle (3 ops)
record("GET", "/products/SMARTPHONE/features", flow_id="flow_features")
record("POST", "/products/SMARTPHONE/features/CAMERA", form_data={"description": "High-Res Camera"}, flow_id="flow_features")
record("PUT", "/products/SMARTPHONE/features/CAMERA", form_data={"description": "4K Ultra-HD Camera"}, flow_id="flow_features")

# 3. Constraints (3 ops)
record("POST", "/products/SMARTPHONE/constraints/requires", form_data={"sourceFeature": "CAMERA", "requiredFeature": "STORAGE"}, flow_id="flow_features")
record("POST", "/products/SMARTPHONE/constraints/excludes", form_data={"sourceFeature": "CAMERA", "excludedFeature": "FM_RADIO"}, flow_id="flow_features")
record("DELETE", "/products/SMARTPHONE/constraints/1", flow_id="flow_features")

# 4. Configurations (7 ops)
record("GET", "/products/SMARTPHONE/configurations", flow_id="flow_features")
record("POST", "/products/SMARTPHONE/configurations/PRO_CONFIG", flow_id="flow_features")
record("GET", "/products/SMARTPHONE/configurations/PRO_CONFIG", flow_id="flow_features")
record("POST", "/products/SMARTPHONE/configurations/PRO_CONFIG/features/CAMERA", flow_id="flow_features")
record("GET", "/products/SMARTPHONE/configurations/PRO_CONFIG/features", flow_id="flow_features")
record("DELETE", "/products/SMARTPHONE/configurations/PRO_CONFIG/features/CAMERA", flow_id="flow_features")
record("DELETE", "/products/SMARTPHONE/configurations/PRO_CONFIG", flow_id="flow_features")

# Cleanups (2 ops)
record("DELETE", "/products/SMARTPHONE/features/CAMERA", flow_id="flow_features")
record("DELETE", "/products/SMARTPHONE", flow_id="flow_features")

with open(OUT_FILE, "w", encoding="utf-8") as f:
    for s in steps: f.write(json.dumps(s, ensure_ascii=False) + "\n")

print(f"\n[SUCCESS] Recorded ALL {len(steps)} operations directly to {OUT_FILE}!")

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

Reset:

```bash
docker restart restgym_features_service
```

---

## 39. Service 4 — `flight-search-api`

Patch RESTgym authentication to register an ADMIN test identity:

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

Recorder:

```text
import json
import os
import requests
import time

PROXY_URL = "http://localhost:9090"
OUT_FILE = "p2s_traces/flight-search/primitive_traces.jsonl"
os.makedirs("p2s_traces/flight-search", exist_ok=True)

# Pre-seeded MongoDB UUIDs from init-mongo.js
ISTANBUL_AIRPORT = "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d"
ANKARA_AIRPORT = "c3d4e5f6-a7b8-6c7d-0e1f-2a3b4c5d6e7f"
FLIGHT_IST_ANK = "f1a2b3c4-d5e6-4f5a-6b7c-8d9e0f1a2b3c"

steps = []
step_cnt = 1

def record(method, path, params=None, json_body=None, flow_id="flow_flightsearch_full"):
    global step_cnt
    url = f"{PROXY_URL}{path}"
    headers = {"Content-Type": "application/json"}

    try:
        if method == "GET": res = requests.get(url, headers=headers, params=params, timeout=10)
        elif method == "POST": res = requests.post(url, headers=headers, params=params, json=json_body, timeout=10)
        elif method == "PUT": res = requests.put(url, headers=headers, params=params, json=json_body, timeout=10)
        elif method == "DELETE": res = requests.delete(url, headers=headers, timeout=10)

        try: res_data = res.json()
        except: res_data = res.text

        full_path_str = path
        if params:
            qp = "&".join([f"{k}={v}" for k, v in params.items()])
            full_path_str += f"?{qp}"

        trace_step = {
            "flow_id": flow_id,
            "step": step_cnt,
            "request": {"method": method, "path": full_path_str, "headers": headers, "body": json_body},
            "response": {"status_code": res.status_code, "body": res_data}
        }
        steps.append(trace_step)
        print(f"  [{step_cnt:>2}/40] {method:6} {full_path_str[:55]:<55} -> {res.status_code}")
        step_cnt += 1
        return res_data
    except Exception as e:
        print(f"  [{step_cnt:>2}/40] ERROR {method} {path}: {e}")
        step_cnt += 1
        return {}

print("=== 1. Checking API Health & Readiness ===")
for _ in range(30):
    try:
        r = requests.get(f"{PROXY_URL}/actuator/health", timeout=1)
        if r.status_code == 200:
            print("  [HEALTHCHECK] Flight Search API is ready!")
            break
    except Exception:
        time.sleep(1)

print("\n=== 2. Recording ALL 40 Operations for Flight Search API ===")

# ── FLOW 1: Auth & User Management (9 ops) ──
ts = int(time.time())
record("POST", "/api/v1/authentication/user/register", json_body={"email": f"user{ts}@test.com", "password": "Password123!", "firstName": "Test", "lastName": "User", "phoneNumber": "12345678901", "userType": "USER"}, flow_id="flow_users")
record("POST", "/api/v1/authentication/user/login", json_body={"email": f"user{ts}@test.com", "password": "Password123!"}, flow_id="flow_users")
record("POST", "/api/v1/authentication/refresh-token", json_body={"refreshToken": "dummy_refresh_token"}, flow_id="flow_users")
record("GET", "/api/v1/users/me", flow_id="flow_users")
record("PUT", "/api/v1/users/me", json_body={"firstName": "UpdatedTest", "lastName": "User", "phoneNumber": "12345678901"}, flow_id="flow_users")
record("GET", "/api/v1/users", flow_id="flow_users")
record("GET", "/api/v1/users/1", flow_id="flow_users")
record("GET", "/api/v1/tokens", flow_id="flow_users")
record("DELETE", "/api/v1/tokens/1", flow_id="flow_users")

# ── FLOW 2: Airports Management (8 ops) ──
record("GET", "/api/v1/airports", flow_id="flow_airports")
apt1 = record("POST", "/api/v1/airports", json_body={"name": "Bodrum Milas Airport", "cityName": "Bodrum"}, flow_id="flow_airports")
apt_id1 = apt1.get("response", {}).get("id") if isinstance(apt1, dict) and isinstance(apt1.get("response"), dict) else ISTANBUL_AIRPORT

record("GET", f"/api/v1/airports/{ISTANBUL_AIRPORT}", flow_id="flow_airports")
record("GET", "/api/v1/airports/search", params={"query": "Istanbul"}, flow_id="flow_airports")
record("GET", "/api/v1/airports/city/Istanbul", flow_id="flow_airports")
record("PUT", f"/api/v1/airports/{ISTANBUL_AIRPORT}", json_body={"name": "Istanbul Int Airport", "cityName": "Istanbul"}, flow_id="flow_airports")
record("POST", "/api/v1/airports/batch", json_body=[{"name": "Izmir Airport", "cityName": "Izmir"}], flow_id="flow_airports")
record("DELETE", f"/api/v1/airports/{apt_id1}", flow_id="flow_airports")

# ── FLOW 3: Flights Management & Search (15 ops) ──
record("GET", "/api/v1/flights", flow_id="flow_flights")
flt = record("POST", "/api/v1/flights", json_body={
    "fromAirportId": ISTANBUL_AIRPORT,
    "toAirportId": ANKARA_AIRPORT,
    "price": 199.99,
    "departureTime": "2026-09-01T10:00:00Z",
    "arrivalTime": "2026-09-01T11:30:00Z"
}, flow_id="flow_flights")
flt_id = flt.get("response", {}).get("id") if isinstance(flt, dict) and isinstance(flt.get("response"), dict) else FLIGHT_IST_ANK

record("GET", f"/api/v1/flights/{FLIGHT_IST_ANK}", flow_id="flow_flights")
record("GET", f"/api/v1/flights/origin/{ISTANBUL_AIRPORT}", flow_id="flow_flights")
record("GET", f"/api/v1/flights/destination/{ANKARA_AIRPORT}", flow_id="flow_flights")
record("GET", "/api/v1/flights/search", params={"fromAirportId": ISTANBUL_AIRPORT, "toAirportId": ANKARA_AIRPORT, "departureTime": "2026-09-01"}, flow_id="flow_flights")
record("GET", "/api/v1/flights/search/cheapest", flow_id="flow_flights")
record("GET", "/api/v1/flights/search/direct", flow_id="flow_flights")

record("PUT", f"/api/v1/flights/{FLIGHT_IST_ANK}", json_body={
    "fromAirportId": ISTANBUL_AIRPORT,
    "toAirportId": ANKARA_AIRPORT,
    "price": 249.99,
    "departureTime": "2026-09-01T10:00:00Z",
    "arrivalTime": "2026-09-01T11:30:00Z"
}, flow_id="flow_flights")

record("POST", "/api/v1/flights/batch", json_body=[{
    "fromAirportId": ISTANBUL_AIRPORT,
    "toAirportId": ANKARA_AIRPORT,
    "price": 150.00,
    "departureTime": "2026-09-02T10:00:00Z",
    "arrivalTime": "2026-09-02T11:30:00Z"
}], flow_id="flow_flights")

record("GET", "/api/v1/flights/price-range", params={"min": 100, "max": 500}, flow_id="flow_flights")
record("GET", "/api/v1/flights/airline/THY", flow_id="flow_flights")
record("GET", "/api/v1/flights/date-range", params={"start": "2026-09-01", "end": "2026-09-30"}, flow_id="flow_flights")
record("PUT", f"/api/v1/flights/{FLIGHT_IST_ANK}/price", params={"price": 299.99}, flow_id="flow_flights")
record("DELETE", f"/api/v1/flights/{flt_id}", flow_id="flow_flights")

# ── FLOW 4: System & Actuator (8 ops) ──
record("GET", "/actuator/health", flow_id="flow_system")
record("GET", "/actuator/info", flow_id="flow_system")
record("GET", "/actuator/metrics", flow_id="flow_system")
record("GET", "/actuator/env", flow_id="flow_system")
record("GET", "/actuator/loggers", flow_id="flow_system")
record("GET", "/v3/api-docs", flow_id="flow_system")
record("GET", "/swagger-ui/index.html", flow_id="flow_system")
record("DELETE", "/api/v1/users/me", flow_id="flow_cleanup")

with open(OUT_FILE, "w", encoding="utf-8") as f:
    for s in steps: f.write(json.dumps(s, ensure_ascii=False) + "\n")

print(f"\n[SUCCESS] Recorded ALL {len(steps)} operations across 4 execution flows directly to {OUT_FILE}!")

```

Copy spec and compile:

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

Evaluate:

```bash
rm -f flightsearch_p2s_processed_flows.txt flightsearch_p2s_golden_dataset.jsonl flightsearch_p2s_silver_dataset.jsonl
python3 eval_student_p2s_engine.py \
  --target-port 9090 \
  --traces p2s_traces/flight-search/compiled_traces.jsonl \
  --catalog p2s_traces/flight-search/flightsearch_ocli_catalog.json \
  --output-prefix flightsearch_p2s \
  --time-budget 3600
```

Fast reset:

```bash
docker exec restgym_flightsearch mongosh flightdatabase --eval 'db.dropDatabase();'
docker exec restgym_flightsearch mongosh flightdatabase /api/database/init-mongo.js
```

---

## 40. Service 5 — `gestao-hospital-api`

```bash
docker rm -f restgym_gestaohospital 2>/dev/null || true
docker build -t restgym/gestaohospital:latest -f apis/gestao-hospital/Dockerfile .
MSYS_NO_PATHCONV=1 docker run -d --name restgym_gestaohospital \
  -p 9090:9090 -p 12345:12345 \
  -e API=gestao-hospital -e TOOL=manual -e RUN=1 \
  restgym/gestaohospital:latest
sleep 20
```

Recorder:

```text
import json
import os
import requests
import time

PROXY_URL = "http://localhost:9090"
OUT_FILE = "p2s_traces/gestao-hospital/primitive_traces.jsonl"
os.makedirs("p2s_traces/gestao-hospital", exist_ok=True)

# Pre-seeded MongoDB ObjectIds from init-mongo.js
HOSPITAL_CENTRAL = "507f1f77bcf86cd799439011"
HOSPITAL_SUL = "507f191e810c19729de860ea"

steps = []
step_cnt = 1

def record(method, path, params=None, json_body=None, flow_id="flow_gestao_full"):
    global step_cnt
    url = f"{PROXY_URL}{path}"
    headers = {"Content-Type": "application/json"}

    try:
        if method == "GET": res = requests.get(url, headers=headers, params=params, timeout=10)
        elif method == "POST": res = requests.post(url, headers=headers, params=params, json=json_body, timeout=10)
        elif method == "PUT": res = requests.put(url, headers=headers, params=params, json=json_body, timeout=10)
        elif method == "DELETE": res = requests.delete(url, headers=headers, timeout=10)

        try: res_data = res.json()
        except: res_data = res.text

        full_path_str = path
        if params:
            qp = "&".join([f"{k}={v}" for k, v in params.items()])
            full_path_str += f"?{qp}"

        trace_step = {
            "flow_id": flow_id,
            "step": step_cnt,
            "request": {"method": method, "path": full_path_str, "headers": headers, "body": json_body},
            "response": {"status_code": res.status_code, "body": res_data}
        }
        steps.append(trace_step)
        print(f"  [{step_cnt:>2}/20] {method:6} {full_path_str[:55]:<55} -> {res.status_code}")
        step_cnt += 1
        return res_data
    except Exception as e:
        print(f"  [{step_cnt:>2}/20] ERROR {method} {path}: {e}")
        step_cnt += 1
        return {}

print("=== 1. Checking API Health & Readiness ===")
for _ in range(30):
    try:
        r = requests.get(f"http://localhost:8080/v1/hospitais/", timeout=1)
        if r.status_code in [200, 401, 403]:  # Any response means Tomcat is up
            print("  [HEALTHCHECK] Gestao Hospitalar API is ready!")
            break
    except Exception:
        time.sleep(1)

print("\n=== 2. Recording ALL 20 Operations for Gestao Hospitalar ===")

# ── FLOW 1: Hospitals & Geospatial (8 ops) ──
record("GET", "/v1/hospitais/", flow_id="flow_hospitals")
h1 = record("POST", "/v1/hospitais/", json_body={"name": "Hospital Norte", "address": "Av Norte 500", "latitude": "-23.50", "longitude": "-46.60", "beds": 100, "availableBeds": 25}, flow_id="flow_hospitals")
h_id = h1.get("id") if isinstance(h1, dict) else HOSPITAL_CENTRAL

record("GET", f"/v1/hospitais/{h_id}", flow_id="flow_hospitals")
record("PUT", f"/v1/hospitais/{h_id}", json_body={"name": "Hospital Norte Atualizado", "address": "Av Norte 500", "latitude": "-23.50", "longitude": "-46.60", "beds": 120, "availableBeds": 30}, flow_id="flow_hospitals")
record("GET", f"/v1/hospitais/{h_id}/leitos", flow_id="flow_hospitals")
record("GET", "/v1/hospitais/maisProximo", params={"lat": -23.5505, "lon": -46.6333, "raioMaximo": 10.0}, flow_id="flow_hospitals")
record("GET", f"/v1/hospitais/{HOSPITAL_CENTRAL}/hospitaisProximos", params={"raio": 15.0}, flow_id="flow_hospitals")
record("DELETE", f"/v1/hospitais/{h_id}", flow_id="flow_hospitals")

# ── FLOW 2: Medical Stock & Transfers (6 ops) ──
record("GET", f"/v1/hospitais/{HOSPITAL_CENTRAL}/estoque", flow_id="flow_stock")
p1 = record("POST", f"/v1/hospitais/{HOSPITAL_CENTRAL}/estoque", json_body={"name": "Soro Fisiologico", "productName": "Soro", "productType": "COMMON", "quantity": 100, "description": "Solucao 500ml"}, flow_id="flow_stock")
p_id = p1.get("id") if isinstance(p1, dict) else "673e1f77bcf86cd799439099"

record("GET", f"/v1/hospitais/{HOSPITAL_CENTRAL}/estoque/{p_id}", flow_id="flow_stock")
record("PUT", f"/v1/hospitais/{HOSPITAL_CENTRAL}/estoque/{p_id}", json_body={"name": "Soro Fisiologico", "productName": "Soro", "productType": "COMMON", "quantity": 150, "description": "Solucao 500ml"}, flow_id="flow_stock")
record("POST", f"/v1/hospitais/{HOSPITAL_CENTRAL}/transferencia/{p_id}", json_body=50, flow_id="flow_stock") # Sends an int body
record("DELETE", f"/v1/hospitais/{HOSPITAL_CENTRAL}/estoque/{p_id}", flow_id="flow_stock")

# ── FLOW 3: Patients Check-In/Check-Out (5 ops) ──
record("GET", f"/v1/hospitais/{HOSPITAL_CENTRAL}/pacientes", flow_id="flow_patients")
pat1 = record("POST", f"/v1/hospitais/{HOSPITAL_CENTRAL}/pacientes/checkin", json_body={"name": "Carlos Eduardo", "cpf": "12345678901", "gender": "MASCULINO", "active": True}, flow_id="flow_patients")
pat_id = pat1.get("id") if isinstance(pat1, dict) else "673e1f77bcf86cd799439111"

record("GET", f"/v1/hospitais/{HOSPITAL_CENTRAL}/pacientes/{pat_id}", flow_id="flow_patients")
record("PUT", f"/v1/hospitais/{HOSPITAL_CENTRAL}/pacientes/{pat_id}", json_body={"name": "Carlos Eduardo Atualizado", "cpf": "12345678901", "gender": "MASCULINO", "active": True}, flow_id="flow_patients")
record("POST", f"/v1/hospitais/{HOSPITAL_CENTRAL}/pacientes/checkout", json_body=pat_id, flow_id="flow_patients") # Sends string body

# ── FLOW 4: Nearby Locations (1 op) ──
record("GET", f"/v1/hospitais/{HOSPITAL_CENTRAL}/proximidades", flow_id="flow_locations")

with open(OUT_FILE, "w", encoding="utf-8") as f:
    for s in steps: f.write(json.dumps(s, ensure_ascii=False) + "\n")

print(f"\n[SUCCESS] Recorded ALL {len(steps)} operations directly to {OUT_FILE}!")

```

Run/compile/evaluate:

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

Fast reset:

```bash
docker exec restgym_gestaohospital mongosh HospitalDB --eval 'db.dropDatabase();'
docker exec restgym_gestaohospital mongosh HospitalDB /api/database/init-mongo.js
```

---

## 41. Service 6 — `kafka-rest-proxy-api`

```bash
docker rm -f restgym_kafkarest 2>/dev/null || true
docker build -t restgym/kafkarest:latest -f apis/kafka-rest-proxy/Dockerfile .
MSYS_NO_PATHCONV=1 docker run -d --name restgym_kafkarest \
  -p 9090:9090 -p 12345:12345 \
  -e API=kafka-rest-proxy -e TOOL=manual -e RUN=1 \
  restgym/kafkarest:latest
sleep 30
```

Recorder:

```text
import json
import os
import requests
import time

PROXY_URL = "http://localhost:9090"
OUT_FILE = "p2s_traces/kafka-rest-proxy/primitive_traces.jsonl"
os.makedirs("p2s_traces/kafka-rest-proxy", exist_ok=True)

steps = []
step_cnt = 1

def record(method, path, params=None, json_body=None, headers=None, flow_id="flow_kafkarest_full"):
    global step_cnt
    url = f"{PROXY_URL}{path}"
    req_headers = headers or {"Content-Type": "application/json"}

    try:
        if method == "GET": res = requests.get(url, headers=req_headers, params=params, timeout=10)
        elif method == "POST": res = requests.post(url, headers=req_headers, params=params, json=json_body, timeout=10)
        elif method == "PUT": res = requests.put(url, headers=req_headers, params=params, json=json_body, timeout=10)
        elif method == "DELETE": res = requests.delete(url, headers=req_headers, timeout=10)

        try: res_data = res.json()
        except: res_data = res.text

        full_path_str = path
        if params:
            qp = "&".join([f"{k}={v}" for k, v in params.items()])
            full_path_str += f"?{qp}"

        trace_step = {
            "flow_id": flow_id,
            "step": step_cnt,
            "request": {"method": method, "path": full_path_str, "headers": req_headers, "body": json_body},
            "response": {"status_code": res.status_code, "body": res_data}
        }
        steps.append(trace_step)
        print(f"  [{step_cnt:>2}/50] {method:6} {full_path_str[:55]:<55} -> {res.status_code}")
        step_cnt += 1
        return res_data
    except Exception as e:
        print(f"  [{step_cnt:>2}/50] ERROR {method} {path}: {e}")
        step_cnt += 1
        return {}

print("=== 1. Checking API Health & Readiness ===")
for _ in range(30):
    try:
        r = requests.get(f"{PROXY_URL}/v3/clusters", timeout=1)
        if r.status_code == 200:
            print("  [HEALTHCHECK] Kafka REST Proxy is ready!")
            break
    except Exception:
        time.sleep(1)

# Dynamically extract the Kafka Cluster ID
cluster_data = requests.get(f"{PROXY_URL}/v3/clusters").json()
CLUSTER_ID = cluster_data.get("data", [{}])[0].get("cluster_id", "MkU3OEVBNTcwNTJENDM2Qk")
print(f"  [INFO] Discovered Cluster ID: {CLUSTER_ID}")

# Clear topic if it exists
os.system("docker exec restgym_kafkarest kafka-topics --bootstrap-server localhost:9092 --delete --topic p2s-topic >/dev/null 2>&1")
time.sleep(1)

print("\n=== 2. Recording ALL 50 Operations for Kafka REST Proxy ===")

# ── FLOW 1: Cluster & Broker Metadata (v3) ──
record("GET", "/v3/clusters", flow_id="flow_cluster")
record("GET", f"/v3/clusters/{CLUSTER_ID}", flow_id="flow_cluster")
record("GET", f"/v3/clusters/{CLUSTER_ID}/brokers", flow_id="flow_cluster")
record("GET", f"/v3/clusters/{CLUSTER_ID}/brokers/1", flow_id="flow_cluster")
record("GET", f"/v3/clusters/{CLUSTER_ID}/broker-configs", flow_id="flow_cluster")
record("GET", f"/v3/clusters/{CLUSTER_ID}/brokers/1/configs", flow_id="flow_cluster")

# ── FLOW 2: Topics, Partitions & Replicas (v3) ──
record("POST", f"/v3/clusters/{CLUSTER_ID}/topics", json_body={"topic_name":"p2s-topic","partitions_count":1,"replication_factor":1}, flow_id="flow_topics")
record("GET", f"/v3/clusters/{CLUSTER_ID}/topics", flow_id="flow_topics")
record("GET", f"/v3/clusters/{CLUSTER_ID}/topics/p2s-topic", flow_id="flow_topics")
record("GET", f"/v3/clusters/{CLUSTER_ID}/topics/p2s-topic/configs", flow_id="flow_topics")
record("GET", f"/v3/clusters/{CLUSTER_ID}/topics/p2s-topic/partitions", flow_id="flow_topics")
record("GET", f"/v3/clusters/{CLUSTER_ID}/topics/p2s-topic/partitions/0", flow_id="flow_topics")
record("GET", f"/v3/clusters/{CLUSTER_ID}/topics/p2s-topic/partitions/0/replicas", flow_id="flow_topics")
record("GET", f"/v3/clusters/{CLUSTER_ID}/topics/p2s-topic/partitions/0/replicas/1", flow_id="flow_topics")

# ── FLOW 3: Message Production (v3) ──
record("POST", f"/v3/clusters/{CLUSTER_ID}/topics/p2s-topic/records", json_body={"value":{"type":"JSON","data":{"msg":"hello p2s"}}}, flow_id="flow_produce")
record("POST", f"/v3/clusters/{CLUSTER_ID}/topics/p2s-topic/records", json_body={"partition_id": 0, "value":{"type":"JSON","data":{"msg":"hello partition"}}}, flow_id="flow_produce")

# ── FLOW 4: Legacy APIs & Brokers (v2) ──
record("GET", "/brokers", flow_id="flow_v2")
record("GET", "/topics", flow_id="flow_v2")
record("GET", "/topics/p2s-topic", flow_id="flow_v2")
record("GET", "/topics/p2s-topic/partitions", flow_id="flow_v2")
record("GET", "/topics/p2s-topic/partitions/0", flow_id="flow_v2")
v2_headers = {"Content-Type": "application/vnd.kafka.json.v2+json", "Accept": "application/vnd.kafka.v2+json"}
record("POST", "/topics/p2s-topic", headers=v2_headers, json_body={"records":[{"value":{"test":"data"}}]}, flow_id="flow_v2")
record("POST", "/topics/p2s-topic/partitions/0", headers=v2_headers, json_body={"records":[{"value":{"test":"data2"}}]}, flow_id="flow_v2")

# ── FLOW 5: Consumer Groups & Subscription (v2 & v3) ──
record("GET", f"/v3/clusters/{CLUSTER_ID}/consumer-groups", flow_id="flow_consumers")
record("POST", "/consumers/p2s-group", headers={"Content-Type": "application/vnd.kafka.v2+json"}, json_body={"name":"p2s_consumer","format":"json","auto.offset.reset":"earliest"}, flow_id="flow_consumers")
record("POST", "/consumers/p2s-group/instances/p2s_consumer/subscription", headers={"Content-Type": "application/vnd.kafka.v2+json"}, json_body={"topics":["p2s-topic"]}, flow_id="flow_consumers")
record("GET", "/consumers/p2s-group/instances/p2s_consumer/subscription", headers={"Accept": "application/vnd.kafka.v2+json"}, flow_id="flow_consumers")

# Seek & Commit operations
record("POST", "/consumers/p2s-group/instances/p2s_consumer/assignments", headers={"Content-Type": "application/vnd.kafka.v2+json"}, json_body={"partitions":[{"topic":"p2s-topic","partition":0}]}, flow_id="flow_consumers")
record("POST", "/consumers/p2s-group/instances/p2s_consumer/positions", headers={"Content-Type": "application/vnd.kafka.v2+json"}, json_body={"offsets":[{"topic":"p2s-topic","partition":0,"offset":0}]}, flow_id="flow_consumers")
record("POST", "/consumers/p2s-group/instances/p2s_consumer/positions/beginning", headers={"Content-Type": "application/vnd.kafka.v2+json"}, json_body={"partitions":[{"topic":"p2s-topic","partition":0}]}, flow_id="flow_consumers")
record("POST", "/consumers/p2s-group/instances/p2s_consumer/positions/end", headers={"Content-Type": "application/vnd.kafka.v2+json"}, json_body={"partitions":[{"topic":"p2s-topic","partition":0}]}, flow_id="flow_consumers")
record("POST", "/consumers/p2s-group/instances/p2s_consumer/offsets", headers={"Content-Type": "application/vnd.kafka.v2+json"}, json_body={"offsets":[{"topic":"p2s-topic","partition":0,"offset":1}]}, flow_id="flow_consumers")
record("GET", "/consumers/p2s-group/instances/p2s_consumer/offsets", headers={"Accept": "application/vnd.kafka.v2+json"}, json_body={"partitions":[{"topic":"p2s-topic","partition":0}]}, flow_id="flow_consumers")

# Consume Messages
record("GET", "/consumers/p2s-group/instances/p2s_consumer/records", headers={"Accept": "application/vnd.kafka.json.v2+json"}, flow_id="flow_consumers")

# Teardown consumers
record("DELETE", "/consumers/p2s-group/instances/p2s_consumer/subscription", headers={"Accept": "application/vnd.kafka.v2+json"}, flow_id="flow_consumers")
record("DELETE", "/consumers/p2s-group/instances/p2s_consumer", headers={"Accept": "application/vnd.kafka.v2+json"}, flow_id="flow_consumers")
record("DELETE", f"/v3/clusters/{CLUSTER_ID}/consumer-groups/p2s-group", flow_id="flow_consumers")

# ── FLOW 6: Cleanup ──
record("DELETE", f"/v3/clusters/{CLUSTER_ID}/topics/p2s-topic", flow_id="flow_cleanup")

# Fill the rest to 50 with ACLs/Configs checks (which often return 400/403 dynamically but exist in spec)
record("GET", f"/v3/clusters/{CLUSTER_ID}/acls", flow_id="flow_cleanup")
record("POST", f"/v3/clusters/{CLUSTER_ID}/acls", json_body={"resource_type":"TOPIC","resource_name":"p2s-topic","pattern_type":"LITERAL","principal":"User:*","host":"*","operation":"ALL","permission":"ALLOW"}, flow_id="flow_cleanup")
record("GET", f"/v3/clusters/{CLUSTER_ID}/broker-configs/log.retention.ms", flow_id="flow_cleanup")
record("GET", f"/v3/clusters/{CLUSTER_ID}/brokers/1/configs/log.retention.ms", flow_id="flow_cleanup")
record("GET", f"/v3/clusters/{CLUSTER_ID}/topics/p2s-topic/configs/cleanup.policy", flow_id="flow_cleanup")

with open(OUT_FILE, "w", encoding="utf-8") as f:
    for s in steps: f.write(json.dumps(s, ensure_ascii=False) + "\n")

print(f"\n[SUCCESS] Recorded ALL {len(steps)} operations directly to {OUT_FILE}!")

```

Compile/evaluate:

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

Fast reset:

```bash
docker exec restgym_kafkarest kafka-topics \
  --bootstrap-server localhost:9092 \
  --delete --topic p2s-topic
```

JaCoCo needs to target the Confluent application classes (for example `io/confluent/**`) rather than unrelated dependencies.

---

## 42. Service 7 — `market-api`

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

Recorder:

```text
import json
import os
import requests
import time

PROXY_URL = "http://localhost:9090"
OUT_FILE = "p2s_traces/market/primitive_traces.jsonl"
os.makedirs("p2s_traces/market", exist_ok=True)

steps = []
step_cnt = 1

def record(method, path, params=None, json_body=None, flow_id="flow_market_full"):
    global step_cnt
    url = f"{PROXY_URL}{path}"
    headers = {"Content-Type": "application/json"}

    try:
        if method == "GET": res = requests.get(url, headers=headers, params=params, timeout=10)
        elif method == "POST": res = requests.post(url, headers=headers, params=params, json=json_body, timeout=10)
        elif method == "PUT": res = requests.put(url, headers=headers, params=params, json=json_body, timeout=10)
        elif method == "DELETE": res = requests.delete(url, headers=headers, timeout=10)

        try: res_data = res.json()
        except: res_data = res.text

        full_path_str = path
        if params:
            qp = "&".join([f"{k}={v}" for k, v in params.items()])
            full_path_str += f"?{qp}"

        trace_step = {
            "flow_id": flow_id,
            "step": step_cnt,
            "request": {"method": method, "path": full_path_str, "headers": headers, "body": json_body},
            "response": {"status_code": res.status_code, "body": res_data}
        }
        steps.append(trace_step)
        print(f"  [{step_cnt:>2}/13] {method:6} {full_path_str[:55]:<55} -> {res.status_code}")
        step_cnt += 1
        return res_data
    except Exception as e:
        print(f"  [{step_cnt:>2}/13] ERROR {method} {path}: {e}")
        step_cnt += 1
        return {}

print("=== 1. Checking API Health & Readiness ===")
for _ in range(30):
    try:
        r = requests.get(f"{PROXY_URL}/products", timeout=1)
        if r.status_code in [200, 401, 403]:  # Any response means Tomcat is up
            print("  [HEALTHCHECK] Market API is ready!")
            break
    except Exception:
        time.sleep(1)

print("\n=== 2. Recording ALL 13 Operations for Market API ===")

# ── FLOW 1: Auth & User Profile (3 ops) ──
ts = int(time.time())
record("POST", "/register", json_body={"email": f"new_customer_{ts}@test.com", "password": "Password123!", "name": "New Customer", "address": "123 Main St", "phone": "+1234567890"}, flow_id="flow_profile")
record("GET", "/customer", flow_id="flow_profile")
record("GET", "/customer/contacts", flow_id="flow_profile")
record("PUT", "/customer/contacts", json_body={"address": "456 Updated Ave", "phone": "+1987654321"}, flow_id="flow_profile")

# ── FLOW 2: Product Browsing (2 ops) ──
record("GET", "/products", flow_id="flow_shopping")
# Pre-seeded product ID 2 is "Uigeadail" from data.sql
record("GET", "/products/2", flow_id="flow_shopping")

# ── FLOW 3: Shopping Cart & Checkout Lifecycle (5 ops) ──
record("GET", "/customer/cart", flow_id="flow_shopping")
# Add product ID 2 to cart
record("PUT", "/customer/cart", json_body={"productId": 2, "quantity": 1}, flow_id="flow_shopping")
# Include delivery
record("PUT", "/customer/cart/delivery", params={"included": "true"}, flow_id="flow_shopping")
# Pay and Checkout
order_resp = record("POST", "/customer/cart/pay", json_body={"ccNumber": "1111222233334444"}, flow_id="flow_shopping")
order_id = order_resp.get("id", 1) if isinstance(order_resp, dict) else 1

# ── FLOW 4: Order History & Cleanup (3 ops) ──
record("GET", "/customer/orders", flow_id="flow_orders")
record("GET", f"/customer/orders/{order_id}", flow_id="flow_orders")
record("DELETE", "/customer/cart", flow_id="flow_orders")

with open(OUT_FILE, "w", encoding="utf-8") as f:
    for s in steps: f.write(json.dumps(s, ensure_ascii=False) + "\n")

print(f"\n[SUCCESS] Recorded ALL {len(steps)} operations directly to {OUT_FILE}!")

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

Reset:

```bash
docker restart restgym_market
```

---

## 43. Service 8 — `notebook-manager-api`

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

Recorder:

```text
import json
import os
import requests
import time

PROXY_URL = "http://localhost:9090"
OUT_FILE = "p2s_traces/notebook-manager/primitive_traces.jsonl"
os.makedirs("p2s_traces/notebook-manager", exist_ok=True)

steps = []
step_cnt = 1

def record(method, path, params=None, json_body=None, flow_id="flow_notebook_full"):
    global step_cnt
    url = f"{PROXY_URL}{path}"
    headers = {"Content-Type": "application/json"}

    try:
        if method == "GET": res = requests.get(url, headers=headers, params=params, timeout=10)
        elif method == "POST": res = requests.post(url, headers=headers, params=params, json=json_body, timeout=10)
        elif method == "PATCH": res = requests.patch(url, headers=headers, params=params, json=json_body, timeout=10)
        elif method == "DELETE": res = requests.delete(url, headers=headers, timeout=10)

        try: res_data = res.json()
        except: res_data = res.text

        full_path_str = path
        if params:
            qp = "&".join([f"{k}={v}" for k, v in params.items()])
            full_path_str += f"?{qp}"

        trace_step = {
            "flow_id": flow_id,
            "step": step_cnt,
            "request": {"method": method, "path": full_path_str, "headers": headers, "body": json_body},
            "response": {"status_code": res.status_code, "body": res_data}
        }
        steps.append(trace_step)
        print(f"  [{step_cnt:>2}/5] {method:6} {full_path_str[:55]:<55} -> {res.status_code}")
        step_cnt += 1
        return res_data
    except Exception as e:
        print(f"  [{step_cnt:>2}/5] ERROR {method} {path}: {e}")
        step_cnt += 1
        return {}

print("=== 1. Checking API Health & Readiness ===")
for _ in range(30):
    try:
        # Check if Tomcat is up by hitting the root or notebooks endpoint
        r = requests.get(f"{PROXY_URL}/api/notebooks", params={"page":0, "pageSize":1}, timeout=1)
        if r.status_code in [200, 400, 404]: 
            print("  [HEALTHCHECK] Notebook Manager API is ready!")
            break
    except Exception:
        time.sleep(1)

print("\n=== 2. Recording ALL 5 Operations for Notebook Manager ===")

# 1. Get Paginated List (Pre-seeded DB has 6 items)
record("GET", "/api/notebooks", params={"page": 0, "pageSize": 10}, flow_id="flow_inventory")

# 2. Create a new notebook
nb_resp = record("POST", "/api/notebooks", json_body={"name": "Lenovo ThinkPad P1", "currentPrice": 1299.99}, flow_id="flow_inventory")
nb_id = nb_resp.get("id", 7) if isinstance(nb_resp, dict) else 7

# 3. Retrieve the newly created notebook
record("GET", f"/api/notebooks/{nb_id}", flow_id="flow_inventory")

# 4. Patch/Update the notebook
record("PATCH", f"/api/notebooks/{nb_id}", json_body={"name": "Lenovo ThinkPad P1 Gen 5", "currentPrice": 1499.99}, flow_id="flow_inventory")

# 5. Delete the notebook
record("DELETE", f"/api/notebooks/{nb_id}", flow_id="flow_inventory")

with open(OUT_FILE, "w", encoding="utf-8") as f:
    for s in steps: f.write(json.dumps(s, ensure_ascii=False) + "\n")

print(f"\n[SUCCESS] Recorded ALL {len(steps)} operations directly to {OUT_FILE}!")

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

The retained Track B adapter uses fast SQL schema/data re-import for state reset. If the published local branch has that reset helper, preserve it verbatim and invoke it through the research runner rather than silently replacing it with a slower container restart.

---

## 44. Service 9 — `person-controller-api`

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

Recorder:

```text
import json
import os
import requests
import time

PROXY_URL = "http://localhost:9090"
OUT_FILE = "p2s_traces/person-controller/primitive_traces.jsonl"
os.makedirs("p2s_traces/person-controller", exist_ok=True)

steps = []
step_cnt = 1

def record(method, path, params=None, json_body=None, flow_id="flow_person_full"):
    global step_cnt
    url = f"{PROXY_URL}{path}"
    headers = {"Content-Type": "application/json"}

    try:
        if method == "GET": res = requests.get(url, headers=headers, params=params, timeout=10)
        elif method == "POST": res = requests.post(url, headers=headers, params=params, json=json_body, timeout=10)
        elif method == "PUT": res = requests.put(url, headers=headers, params=params, json=json_body, timeout=10)
        elif method == "DELETE": res = requests.delete(url, headers=headers, params=params, timeout=10)

        try: res_data = res.json()
        except: res_data = res.text

        full_path_str = path
        if params:
            qp = "&".join([f"{k}={v}" for k, v in params.items()])
            full_path_str += f"?{qp}"

        trace_step = {
            "flow_id": flow_id,
            "step": step_cnt,
            "request": {"method": method, "path": full_path_str, "headers": headers, "body": json_body},
            "response": {"status_code": res.status_code, "body": res_data}
        }
        steps.append(trace_step)
        print(f"  [{step_cnt:>2}/12] {method:6} {full_path_str[:55]:<55} -> {res.status_code}")
        step_cnt += 1
        return res_data
    except Exception as e:
        print(f"  [{step_cnt:>2}/12] ERROR {method} {path}: {e}")
        step_cnt += 1
        return {}

print("=== 1. Checking API Health & Readiness ===")
for _ in range(30):
    try:
        r = requests.get(f"{PROXY_URL}/api/persons/count", timeout=1)
        if r.status_code in [200, 401, 403, 404]: 
            print("  [HEALTHCHECK] Person Controller API is ready!")
            break
    except Exception:
        time.sleep(1)

print("\n=== 2. Recording ALL 12 Operations for Person Controller ===")

# Valid Person Payload
person_payload = {
    "firstName": "John",
    "lastName": "Doe",
    "age": 30,
    "insurance": True,
    "address": {
        "street": "Main St",
        "number": 123,
        "city": "New York",
        "country": "United States",
        "postcode": "10001"
    },
    "cars": [
        {"brand": "Tesla", "model": "Model 3", "maxSpeedKmH": 220.0}
    ]
}

# ── FLOW 1: Single Person Operations (4 ops) ──
p1 = record("POST", "/api/person", json_body=person_payload, flow_id="flow_single")
# Extract Mongo ID if it's a string, or use dummy if Spring returns the raw ObjectId struct
p_id = "60f1b2b3b3b3b3b3b3b3b3b3"
if isinstance(p1, dict):
    if isinstance(p1.get("id"), str): p_id = p1["id"]
    elif isinstance(p1.get("id"), dict) and "timestamp" in p1["id"]: p_id = str(p1["id"]["timestamp"])

record("GET", f"/api/person/{p_id}", flow_id="flow_single")
person_payload["firstName"] = "John Updated"
record("PUT", "/api/person", json_body=person_payload, flow_id="flow_single")
record("DELETE", f"/api/person/{p_id}", flow_id="flow_single")

# ── FLOW 2: Bulk Operations (4 ops) ──
record("POST", "/api/persons", json_body=[person_payload, person_payload], flow_id="flow_bulk")
record("GET", "/api/persons", flow_id="flow_bulk")
record("PUT", "/api/persons", json_body=[person_payload], flow_id="flow_bulk")
record("DELETE", "/api/persons", flow_id="flow_bulk")

# ── FLOW 3: Aggregate & Multi-ID Operations (4 ops) ──
# Re-seed a couple for aggregation
record("POST", "/api/persons", json_body=[person_payload, person_payload], flow_id="flow_aggregate")

record("GET", "/api/persons/count", flow_id="flow_aggregate")
record("GET", "/api/persons/averageAge", flow_id="flow_aggregate")

# Test comma-separated ID endpoints
multi_ids = f"{p_id},{p_id}"
record("GET", f"/api/persons/{multi_ids}", flow_id="flow_aggregate")
record("DELETE", f"/api/persons/{multi_ids}", flow_id="flow_aggregate")

with open(OUT_FILE, "w", encoding="utf-8") as f:
    for s in steps: f.write(json.dumps(s, ensure_ascii=False) + "\n")

print(f"\n[SUCCESS] Recorded ALL {len(steps)} operations directly to {OUT_FILE}!")

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

Reset:

```bash
docker restart restgym_personcontroller
```

---

## 45. Service 10 — `pet-clinic-api`

Enable service:

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

Recorder:

```text
import json
import os
import requests
import time

PROXY_URL = "http://localhost:9090/petclinic"
OUT_FILE = "p2s_traces/pet-clinic/primitive_traces.jsonl"
os.makedirs("p2s_traces/pet-clinic", exist_ok=True)

steps = []
step_cnt = 1

def record(method, path, params=None, json_body=None, flow_id="flow_petclinic_full"):
    global step_cnt
    url = f"{PROXY_URL}{path}"
    
    # Inject Basic Auth (admin:admin) so requests succeed
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Basic YWRtaW46YWRtaW4="
    }

    try:
        if method == "GET": res = requests.get(url, headers=headers, params=params, timeout=10)
        elif method == "POST": res = requests.post(url, headers=headers, params=params, json=json_body, timeout=10)
        elif method == "PUT": res = requests.put(url, headers=headers, params=params, json=json_body, timeout=10)
        elif method == "DELETE": res = requests.delete(url, headers=headers, params=params, timeout=10)

        try: res_data = res.json()
        except: res_data = res.text

        full_path_str = path
        if params:
            qp = "&".join([f"{k}={v}" for k, v in params.items()])
            full_path_str += f"?{qp}"

        trace_step = {
            "flow_id": flow_id,
            "step": step_cnt,
            "request": {"method": method, "path": full_path_str, "headers": headers, "body": json_body},
            "response": {"status_code": res.status_code, "body": res_data}
        }
        steps.append(trace_step)
        print(f"  [{step_cnt:>2}/35] {method:6} {full_path_str[:55]:<55} -> {res.status_code}")
        step_cnt += 1
        return res_data
    except Exception as e:
        print(f"  [{step_cnt:>2}/35] ERROR {method} {path}: {e}")
        step_cnt += 1
        return {}

print("=== 1. Resetting Database ===")
os.system("docker restart restgym_petclinic")
time.sleep(12)

print("\n=== 2. Recording ALL Operations for PetClinic API ===")

# ── FLOW 1: Vets & Specialties (9 ops) ──
record("GET", "/api/specialties", flow_id="flow_clinic")
spec = record("POST", "/api/specialties", json_body={"name": "Cardiology"}, flow_id="flow_clinic")
sid = spec.get("id", 4) if isinstance(spec, dict) else 4
record("GET", f"/api/specialties/{sid}", flow_id="flow_clinic")
record("PUT", f"/api/specialties/{sid}", json_body={"name": "Advanced Cardiology"}, flow_id="flow_clinic")

record("GET", "/api/vets", flow_id="flow_clinic")
vet = record("POST", "/api/vets", json_body={"firstName": "John", "lastName": "Smith", "specialties": [{"id": sid, "name": "Advanced Cardiology"}]}, flow_id="flow_clinic")
vid = vet.get("id", 7) if isinstance(vet, dict) else 7
record("GET", f"/api/vets/{vid}", flow_id="flow_clinic")
record("PUT", f"/api/vets/{vid}", json_body={"firstName": "John", "lastName": "Smith-Doe", "specialties": [{"id": sid, "name": "Advanced Cardiology"}]}, flow_id="flow_clinic")
record("DELETE", f"/api/vets/{vid}", flow_id="flow_clinic")
record("DELETE", f"/api/specialties/{sid}", flow_id="flow_clinic")

# ── FLOW 2: Pet Types (5 ops) ──
record("GET", "/api/pettypes", flow_id="flow_pets")
ptype = record("POST", "/api/pettypes", json_body={"name": "Parrot"}, flow_id="flow_pets")
ptid = ptype.get("id", 7) if isinstance(ptype, dict) else 7
record("GET", f"/api/pettypes/{ptid}", flow_id="flow_pets")
record("PUT", f"/api/pettypes/{ptid}", json_body={"name": "Macaw"}, flow_id="flow_pets")
record("DELETE", f"/api/pettypes/{ptid}", flow_id="flow_pets")

# ── FLOW 3: Owners, Pets, and Visits (15 ops) ──
record("GET", "/api/owners", flow_id="flow_owners")
record("GET", "/api/owners/*/lastname/Davis", flow_id="flow_owners")
owner = record("POST", "/api/owners", json_body={"firstName": "Alice", "lastName": "Wonderland", "address": "123 Rabbit Hole", "city": "London", "telephone": "1234567890"}, flow_id="flow_owners")
oid = owner.get("id", 11) if isinstance(owner, dict) else 11
record("GET", f"/api/owners/{oid}", flow_id="flow_owners")
record("PUT", f"/api/owners/{oid}", json_body={"firstName": "Alice", "lastName": "Wonderland", "address": "456 Queen St", "city": "London", "telephone": "1234567890"}, flow_id="flow_owners")

record("GET", "/api/pets", flow_id="flow_owners")
pet = record("POST", "/api/pets", json_body={"name": "Cheshire", "birthDate": "2020-01-01", "type": {"id": 1, "name": "cat"}, "ownerId": oid}, flow_id="flow_owners")
pid = pet.get("id", 14) if isinstance(pet, dict) else 14
record("GET", f"/api/pets/{pid}", flow_id="flow_owners")
record("PUT", f"/api/pets/{pid}", json_body={"name": "Cheshire Cat", "birthDate": "2020-01-01", "type": {"id": 1, "name": "cat"}, "ownerId": oid}, flow_id="flow_owners")

record("GET", "/api/visits", flow_id="flow_owners")
visit = record("POST", "/api/visits", json_body={"date": "2026-10-10", "description": "Annual checkup", "petId": pid}, flow_id="flow_owners")
vid = visit.get("id", 5) if isinstance(visit, dict) else 5
record("GET", f"/api/visits/{vid}", flow_id="flow_owners")
record("PUT", f"/api/visits/{vid}", json_body={"date": "2026-10-11", "description": "Rescheduled checkup", "petId": pid}, flow_id="flow_owners")

record("DELETE", f"/api/visits/{vid}", flow_id="flow_owners")
record("DELETE", f"/api/pets/{pid}", flow_id="flow_owners")
record("DELETE", f"/api/owners/{oid}", flow_id="flow_owners")

# ── FLOW 4: Users (2 ops) ──
record("POST", "/api/users", json_body={"username": "newvet", "password": "password123", "enabled": True, "roles": [{"name": "ROLE_VET"}]}, flow_id="flow_users")

with open(OUT_FILE, "w", encoding="utf-8") as f:
    for s in steps: f.write(json.dumps(s, ensure_ascii=False) + "\n")

print(f"\n[SUCCESS] Recorded ALL operations directly to {OUT_FILE}!")

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

The research runner/OCLI profile must use:

```bash
ocli profiles add petclinic_p2s \
  --api-base-url http://localhost:9090/petclinic \
  --openapi-spec "$(pwd)/p2s_traces/pet-clinic/petclinic.json" \
  --api-basic-auth "admin:admin" \
  --command-prefix ""
```

Reset:

```bash
docker restart restgym_petclinic
```

---

## 46. Service 11 — `project-tracking-system`

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

Recorder:

```text
import json
import os
import requests
import time

PROXY_URL = "http://localhost:9090"
OUT_FILE = "p2s_traces/project-tracking-system/primitive_traces.jsonl"
os.makedirs("p2s_traces/project-tracking-system", exist_ok=True)

steps = []
step_cnt = 1

def record(method, path, params=None, json_body=None, flow_id="flow_pts_full"):
    global step_cnt
    url = f"{PROXY_URL}{path}"
    headers = {"Content-Type": "application/json"}

    try:
        if method == "GET": res = requests.get(url, headers=headers, params=params, timeout=10)
        elif method == "POST": res = requests.post(url, headers=headers, params=params, json=json_body, timeout=10)
        elif method == "PUT": res = requests.put(url, headers=headers, params=params, json=json_body, timeout=10)
        elif method == "DELETE": res = requests.delete(url, headers=headers, params=params, timeout=10)

        try: res_data = res.json()
        except: res_data = res.text

        full_path_str = path
        if params:
            qp = "&".join([f"{k}={v}" for k, v in params.items()])
            full_path_str += f"?{qp}"

        trace_step = {
            "flow_id": flow_id,
            "step": step_cnt,
            "request": {"method": method, "path": full_path_str, "headers": headers, "body": json_body},
            "response": {"status_code": res.status_code, "body": res_data}
        }
        steps.append(trace_step)
        print(f"  [{step_cnt:>2}/59] {method:6} {full_path_str[:60]:<60} -> {res.status_code}")
        step_cnt += 1
        return res_data
    except Exception as e:
        print(f"  [{step_cnt:>2}/59] ERROR {method} {path}: {e}")
        step_cnt += 1
        return {}

print("=== 1. Checking API Health & Readiness ===")
for _ in range(30):
    try:
        r = requests.get(f"{PROXY_URL}/app/api/locations", timeout=1)
        if r.status_code in [200, 401, 403]: 
            print("  [HEALTHCHECK] Project Tracking System API is ready!")
            break
    except Exception:
        time.sleep(1)

print("\n=== 2. Recording ALL 59 Operations ===")

# Base Objects for creation
loc_body = {"adr": "123 P2S Ave", "postalCode": "10001", "city": "Fuzz City"}
dept_body = {"departmentName": "Security QA", "location": {"locationId": 1}}
emp_body = {"firstName": "Test", "lastName": "User", "email": "test@test.com", "phone": "123", "job": "Tester", "salary": 5000.0, "department": {"departmentId": 4}}
proj_body = {"title": "P2S Evaluation", "startDate": "2026-08-01", "endDate": "2026-12-31", "status": "IN_PROGRESS"}
cred_body = {"username": "fuzzer", "password": "pwd", "enabled": True, "role": "ROLE_EMP"}

# ── 1. Locations (9 ops) ──
record("GET", "/app/api/locations", flow_id="flow_locations")
loc = record("POST", "/app/api/locations/save", json_body=loc_body, flow_id="flow_locations")
lid = loc.get("locationId", 3) if isinstance(loc, dict) else 3
record("GET", f"/app/api/locations/{lid}", flow_id="flow_locations")
record("PUT", "/app/api/locations/update", json_body={"locationId": lid, "city": "Updated City"}, flow_id="flow_locations")
record("POST", "/app/api/locations", json_body=loc_body, flow_id="flow_locations")
record("PUT", "/app/api/locations", json_body={"locationId": lid, "city": "Updated 2"}, flow_id="flow_locations")
record("DELETE", "/app/api/locations/delete", params={"locationId": lid}, flow_id="flow_locations")
loc2 = record("POST", "/app/api/locations", json_body=loc_body, flow_id="flow_locations")
lid2 = loc2.get("locationId", 4) if isinstance(loc2, dict) else 4
record("DELETE", f"/app/api/locations/{lid2}", flow_id="flow_locations")

# ── 2. Departments (9 ops) ──
record("GET", "/app/api/departments", flow_id="flow_depts")
dept = record("POST", "/app/api/departments/save", json_body=dept_body, flow_id="flow_depts")
did = dept.get("departmentId", 7) if isinstance(dept, dict) else 7
record("GET", f"/app/api/departments/{did}", flow_id="flow_depts")
record("PUT", "/app/api/departments/update", json_body={"departmentId": did, "departmentName": "Updated Dept"}, flow_id="flow_depts")
record("POST", "/app/api/departments", json_body=dept_body, flow_id="flow_depts")
record("PUT", "/app/api/departments", json_body={"departmentId": did, "departmentName": "Updated 2"}, flow_id="flow_depts")
record("DELETE", "/app/api/departments/delete", params={"departmentId": did}, flow_id="flow_depts")
dept2 = record("POST", "/app/api/departments", json_body=dept_body, flow_id="flow_depts")
did2 = dept2.get("departmentId", 8) if isinstance(dept2, dict) else 8
record("DELETE", f"/app/api/departments/{did2}", flow_id="flow_depts")

# ── 3. Projects (10 ops) ──
record("GET", "/app/api/projects", flow_id="flow_projects")
proj = record("POST", "/app/api/projects/save", json_body=proj_body, flow_id="flow_projects")
pid = proj.get("projectId", 10) if isinstance(proj, dict) else 10
record("GET", f"/app/api/projects/{pid}", flow_id="flow_projects")
record("PUT", "/app/api/projects/update", json_body={"projectId": pid, "title": "Updated Proj"}, flow_id="flow_projects")
record("POST", "/app/api/projects", json_body=proj_body, flow_id="flow_projects")
record("PUT", "/app/api/projects", json_body={"projectId": pid, "title": "Updated 2"}, flow_id="flow_projects")
record("DELETE", "/app/api/projects/delete", params={"projectId": pid}, flow_id="flow_projects")
proj2 = record("POST", "/app/api/projects", json_body=proj_body, flow_id="flow_projects")
pid2 = proj2.get("projectId", 11) if isinstance(proj2, dict) else 11
record("DELETE", f"/app/api/projects/{pid2}", flow_id="flow_projects")
record("DELETE", "/app/api/projects/delete", flow_id="flow_projects") # Trigger 400 with missing param

# ── 4. Employees (13 ops) ──
record("GET", "/app/api/employees", flow_id="flow_employees")
emp = record("POST", "/app/api/employees/save", json_body=emp_body, flow_id="flow_employees")
eid = emp.get("employeeId", 15) if isinstance(emp, dict) else 15
record("GET", f"/app/api/employees/{eid}", flow_id="flow_employees")
record("GET", "/app/api/employees/data/department/4", flow_id="flow_employees")
record("GET", "/app/api/employees/data/employee-project-data/1", flow_id="flow_employees")
record("GET", "/app/api/employees/data/manager-project-data/4", flow_id="flow_employees")
record("PUT", "/app/api/employees/update", json_body={"employeeId": eid, "firstName": "Updated"}, flow_id="flow_employees")
record("POST", "/app/api/employees", json_body=emp_body, flow_id="flow_employees")
record("PUT", "/app/api/employees", json_body={"employeeId": eid, "firstName": "Updated 2"}, flow_id="flow_employees")
record("DELETE", "/app/api/employees/delete", params={"employeeId": eid}, flow_id="flow_employees")
emp2 = record("POST", "/app/api/employees", json_body=emp_body, flow_id="flow_employees")
eid2 = emp2.get("employeeId", 16) if isinstance(emp2, dict) else 16
record("DELETE", f"/app/api/employees/username/admin", flow_id="flow_employees")
record("GET", "/app/api/employees/username/admin", flow_id="flow_employees")

# ── 5. Credentials (9 ops) ──
record("GET", "/app/api/credentials", flow_id="flow_credentials")
cred = record("POST", "/app/api/credentials/save", json_body=cred_body, flow_id="flow_credentials")
crid = cred.get("credentialId", 15) if isinstance(cred, dict) else 15
record("GET", f"/app/api/credentials/{crid}", flow_id="flow_credentials")
record("GET", "/app/api/credentials/username/fuzzer", flow_id="flow_credentials")
record("PUT", "/app/api/credentials/update", json_body={"credentialId": crid, "username": "fuzzer_updated"}, flow_id="flow_credentials")
record("POST", "/app/api/credentials", json_body=cred_body, flow_id="flow_credentials")
record("PUT", "/app/api/credentials", json_body={"credentialId": crid, "username": "updated2"}, flow_id="flow_credentials")
record("DELETE", "/app/api/credentials/delete", params={"credentialId": crid}, flow_id="flow_credentials")
record("DELETE", "/app/api/credentials/username/fuzzer_updated", flow_id="flow_credentials")

# ── 6. Assignments & Commits (9 ops) ──
# We use existing DB seeds: Employee 1, Project 1
commit_date = "2020-11-26T10:50:09"
assign_body = {"employeeId": 1, "projectId": 2, "commitEmpDesc": "Test commit", "commitMgrDesc": "Approved"}

record("GET", "/app/api/assignments", flow_id="flow_assignments")
record("GET", "/app/api/assignments/1/1", flow_id="flow_assignments")
record("GET", f"/app/api/assignments/1/1/{commit_date}", flow_id="flow_assignments")
record("GET", "/app/api/assignments/data/project-commit/1", flow_id="flow_assignments")
record("GET", "/app/api/assignments/data/project-commit/1/1", flow_id="flow_assignments")
record("POST", "/app/api/assignments/save", json_body=assign_body, flow_id="flow_assignments")
record("POST", "/app/api/assignments", json_body=assign_body, flow_id="flow_assignments")
record("PUT", "/app/api/assignments/update", json_body=assign_body, flow_id="flow_assignments")
record("PUT", "/app/api/assignments", json_body=assign_body, flow_id="flow_assignments")

with open(OUT_FILE, "w", encoding="utf-8") as f:
    for s in steps: f.write(json.dumps(s, ensure_ascii=False) + "\n")

print(f"\n[SUCCESS] Recorded ALL {len(steps)} operations directly to {OUT_FILE}!")

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

Reset:

```bash
docker restart restgym_projecttrackingsystem
```

This restarts H2 and replays the Flyway migration/seed lifecycle.

---

## 47. Universal Track B Post-Processing

For every service after the one-hour run:

```bash
python dedup_p2s_goldens.py <service>_p2s_golden_dataset.jsonl
python reclassify_vectors.py <service>_p2s both
```

For strict SBFT Fault Detection, count only `actual_status >= 500` before fault-signature deduplication. Do not include HTTP-200 authorization-bypass Goldens in SBFT FD, although they remain valid P2S security findings under P2S's own taxonomy.

### JaCoCo output convention

Normalize the final host-side output to:

```text
results/<service>/code-coverage/coverage.csv
```

or, if the research branch already uses:

```text
results/<service>/code-coverage.csv
```

retain the branch's exact path and document it in the artifact manifest. Do not rename silently after checksums are published.

### Final Track B audit targets

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

These are audit targets for comparing the retained artifact, not values that a fresh stochastic rerun must exactly equal.

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
    ├── p2s_colab_train.ipynb or equivalent retained training notebook
    ├── environment notes
    └── checksums
```

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
