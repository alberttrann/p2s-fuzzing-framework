# Full Research Reproduction with P2S Framework v1.2

This guide reproduces the P2S research while using **one public implementation of P2S** across the source-corpus run, Track A, and Track B. Historical one-off P2S scripts remain archived under `original_reporducibility_docs/` for audit purposes, but they are not the primary execution path here.

**AutoRestTest final-run model:** DeepSeek-V4-Flash. Older local-base-Qwen AutoRestTest templates are archival and are not used for final-run parity.

> Use only isolated systems that you own or are explicitly authorized to test. The research targets described here are local development applications or Dockerized benchmark services.

## 1. Reproduction model

The research has five operational packages:

| Package | Target/tool | Framework-native role |
|---|---|---|
| 1 | AITasker / SourceMarket | P2S proxy → compiler → self-play data generation → dataset builder |
| 2 | SEAL / HackathonBench | P2S proxy → compiler → shared evaluator with P2S FT, base Qwen, and DeepSeek backends |
| 3 | AutoRestTest on SEAL | P2S prepares the target, long-lived auth, and sanitized OpenAPI; AutoRestTest remains the independent baseline |
| 4 | CATS + Schemathesis on SEAL | Same P2S-prepared baseline contract/token; the tools remain independent baselines |
| 5 | 11 RESTgym services | P2S lifecycle patches + shared compiler + shared cyclic fuzzer + configured reset adapter |

The core rule is:

> **No target gets a private P2S compiler or private P2S evaluator in the primary v1.2 workflow.**

The workload scripts are still target-specific because a stateful API cannot be exercised without target-specific valid business flows. They are fixtures, not alternate P2S engines.

## 2. Install

From this source tree:

```bash
python -m venv .venv
source .venv/Scripts/activate      # Git Bash / Windows
# source .venv/bin/activate        # Linux/macOS
python -m pip install --upgrade pip
pip install -e .

p2s --help
python -c "import p2s; print(p2s.__version__)"
```

Expected framework version:

```text
1.2.0
```

On Windows, install/run from Git Bash. v1.2 explicitly dispatches configured lifecycle/reset commands through Bash when it is available, preserving inline environment assignments, `2>/dev/null`, and `|| true` semantics used by the retained procedures.

Install OCLI separately because it is the OpenAPI-to-CLI execution interface used by the paper:

```bash
npm install -g openapi-to-cli
ocli --help
```

## 3. Environment variables

The research configs deliberately do not hard-code local repository locations or third-party credentials.

```bash
export AITASKER_ROOT=/d/aitasker
export SEAL_ROOT=/d/SWP391_SealHackathon_BackEnd
export RESTGYM_ROOT=/d/restgym

# Required only for DeepSeek-backed runs:
export DEEPSEEK_API_KEY='<your-key>'
```

For Notebook Manager Track B, the exact fast MySQL schema/data re-import command was not retained as a stable standalone command in the public source materials. Do not invent one. Supply the reset command from the preserved benchmark branch you are reproducing:

```bash
export P2S_NOTEBOOK_RESET_COMMAND='<exact SQL schema/data re-import command from your retained RESTgym checkout>'
```

For Kafka REST Proxy, if the checkout contains more than one candidate OpenAPI file, point the config to the exact retained specification:

```bash
export P2S_KAFKA_SPEC='apis/kafka-rest-proxy/specifications/<retained-spec>.yaml'
```

## 4. Framework lifecycle commands

A framework-native research config can drive the following lifecycle:

```bash
p2s doctor        --config <config.toml> --workdir <run-dir>
p2s patch         --config <config.toml> --workdir <run-dir>
p2s prepare       --config <config.toml> --workdir <run-dir>
p2s fetch-openapi --config <config.toml> --workdir <run-dir>
p2s auth          --config <config.toml> --workdir <run-dir>
p2s proxy         --config <config.toml> --workdir <run-dir>
p2s record        --config <config.toml> --workdir <run-dir>
p2s compile       --config <config.toml> --workdir <run-dir>
p2s fuzz          --config <config.toml> --workdir <run-dir>
p2s generate-data --config <config.toml> --workdir <run-dir>
p2s prepare-dataset --config <config.toml> --workdir <run-dir>
p2s coverage      --config <config.toml> --workdir <run-dir>
p2s cleanup       --config <config.toml> --workdir <run-dir>
```

Not every target uses every command. In particular, Track B keeps RESTgym's own mitmproxy on historical port `9090`; its retained workload fixtures already write the P2S primitive-trace schema, so `p2s record` freezes that fixture-produced trace rather than replacing RESTgym's semantically active proxy with another proxy.

## 5. Operation 1 — source-corpus generation on AITasker

Config:

```text
configs/research/aitasker_training.toml
```

The source application uses the framework proxy because P2S itself is responsible for trace capture there.

### Terminal A — application

Launch AITasker's AI service and NestJS backend using the retained `feat/hung/SWT-Main` application branch. The NestJS API must be reachable at:

```text
http://localhost:3001
```

and its OpenAPI document at:

```text
http://localhost:3001/api-json
```

The framework config assumes the isolated PostgreSQL research instance used by the source experiment is available at host port `5434` and can create `aitasker_active` / `aitasker_snap`.
The configured seed command explicitly enters AITasker's `backend/` directory before running Prisma, matching the working directory of the retained generator while keeping that behavior declarative in `aitasker_training.toml`.

### Terminal B — P2S proxy

```bash
p2s prepare \
  --config configs/research/aitasker_training.toml \
  --workdir runs/aitasker

p2s proxy \
  --config configs/research/aitasker_training.toml \
  --workdir runs/aitasker
```

The proxy listens on `8090` and forwards to AITasker `3001`.

### Terminal C — workload capture

```bash
p2s record \
  --config configs/research/aitasker_training.toml \
  --workdir runs/aitasker
```

The configured workload runs AITasker's full mainflow suite against the proxy. `p2s record` then freezes the captured baseline as:

```text
runs/aitasker/baseline_primitive_traces.jsonl
```

### Compile and generate execution-grounded data

Serve **base Qwen3.5-9B** at `http://localhost:1234/v1`, then:

```bash
p2s compile \
  --config configs/research/aitasker_training.toml \
  --workdir runs/aitasker

p2s generate-data \
  --config configs/research/aitasker_training.toml \
  --workdir runs/aitasker

p2s prepare-dataset \
  --config configs/research/aitasker_training.toml \
  --workdir runs/aitasker
```

The paper's retained corpus audit target is 1,782 deduplicated silver records, 44 unique execution-positive candidate goldens, and 2,266 final SFT samples after the retained oversampling procedure. A fresh stochastic rerun need not reproduce the exact 44 positives; record model/build/seed/environment metadata and compare rather than forcing the count.

### Trace-secret note

The historical source-corpus trace compiler consumed controlled disposable bearer values. `aitasker_training.toml` therefore leaves sensitive-header masking disabled for parity. Treat those traces as private research artifacts and sanitize credentials before publication.

## 6. Train and serve the specialist

See [MODEL_AND_TRAINING.md](MODEL_AND_TRAINING.md). The framework produces the final training JSONL; the Colab/Unsloth notebook is the downstream trainer used for the paper.

After conversion, serve the P2S Q8_0 GGUF at:

```text
http://localhost:8081/v1
```

## 7. Operation 2 — Track A on SEAL/HackathonBench

Use the same compiled trace and shared framework evaluator, changing only the model configuration:

```text
configs/research/track_a_seal_p2s.toml
configs/research/track_a_seal_base_qwen.toml
configs/research/track_a_seal_deepseek.toml
```

Detailed target preparation, state reset, recording, OpenAPI relaxation, credentials, and post-hoc verification are in [TRACK_A_WITH_P2S_FRAMEWORK.md](TRACK_A_WITH_P2S_FRAMEWORK.md).

Conceptually:

```bash
# P2S specialist
p2s prepare --config configs/research/track_a_seal_p2s.toml --workdir runs/track-a/p2s
p2s proxy   --config configs/research/track_a_seal_p2s.toml --workdir runs/track-a/p2s
# another terminal:
p2s record  --config configs/research/track_a_seal_p2s.toml --workdir runs/track-a/p2s
p2s compile --config configs/research/track_a_seal_p2s.toml --workdir runs/track-a/p2s
p2s fuzz    --config configs/research/track_a_seal_p2s.toml --workdir runs/track-a/p2s
```

Reuse the frozen primitive/compiled trace for the two controls when possible so the experimental difference is the inference backend, not a new workload recording.

## 8. Operations 3–4 — independent Track-A baselines

Use:

```text
configs/research/track_a_baselines.toml
```

P2S v1.2 owns the **environment equalisation**:

- patch SEAL to issue a 525,600-minute test JWT for the five-hour baseline;
- fetch the current SpringDoc OpenAPI document;
- set the server URL to `http://localhost:8080/api`;
- remove `/auth/logout` and self-deletion operations;
- clear stale revoked tokens;
- obtain and persist a fresh Coordinator bearer token.

AutoRestTest, CATS, and Schemathesis themselves stay unmodified independent tools except for the historical AutoRestTest compatibility/socket patches documented in the Track-A guide.

**Authoritative AutoRestTest model:** the completed research run used **DeepSeek-V4-Flash**. Any older local-base-Qwen AutoRestTest configuration template is archival/stale and is not the final-run parity configuration.

## 9. Operation 5 — Track B on RESTgym

All 11 target configs live under:

```text
configs/research/track_b/
```

For one service:

```bash
CFG=configs/research/track_b/blog.toml
RUN=runs/track-b/blog

p2s prepare --config "$CFG" --workdir "$RUN"
p2s record  --config "$CFG" --workdir "$RUN"
p2s compile --config "$CFG" --workdir "$RUN"
p2s fuzz    --config "$CFG" --workdir "$RUN"
```

The config supplies the one-hour `3600` second budget, cyclic traversal, reset-before-target behavior, strict Track-B 2xx candidate guard, OCLI profile, and service-specific reset primitive.

Do **not** start `p2s proxy` for the retained Track-B protocol. RESTgym's own mitmproxy remains on host `9090` because it performs service-specific authentication and, for ERC20, contract-address rewriting. The `record_*` workload fixtures hit that historical port and emit P2S primitive traces. `p2s record` freezes them; everything after that is the shared v1.2 package.

See [TRACK_B_WITH_P2S_FRAMEWORK.md](TRACK_B_WITH_P2S_FRAMEWORK.md) for all 11 Phase-1 patches and reset contracts.

## 10. Framework-native versus historical-parity artifacts

Use the primary v1.2 workflow for a new rerun. Use `original_reporducibility_docs/` only when you need to answer questions such as:

- What exactly did the original Windows evaluator script do internally?
- Which one-off workaround originally motivated a v1.2 configuration field?
- Why was a particular RESTgym Dockerfile/auth patch introduced?
- What did the original post-hoc helper inspect?

Do not mix an archived private evaluator with the v1.2 evaluator halfway through a run and then call the result a framework-native reproduction.

## 11. Expected reported-result boundaries

For research comparisons, keep these constructs separate:

- **candidate golden** produced by the engine;
- **verified Track-A outcome** after semantic post-hoc validation;
- **strict Track-B 5xx FD proxy**, which excludes 2xx security candidates;
- operation/source coverage;
- state/trace depth.

For each Track-B service, use the framework's status-aware counter:

```bash
p2s fd \
  --golden-file runs/track-b/<service>/<service>_p2s_golden_dataset.jsonl \
  --dedup-out runs/track-b/<service>/<service>_strict_5xx_dedup.jsonl
```

`p2s fd` filters to HTTP 5xx **before** deduplication, so guarded 2xx security-intent Goldens cannot inflate the SBFT-style FD proxy.

The final Track-B strict status-aligned count is 321 deduplicated 5xx signatures across the 11 services, or 29.18/API. Track-B 2xx security-intent labels remain candidates and are not added to the SBFT 5xx FD number. Do not synthesize a P2S Roadrunner/AUC score from final endpoint snapshots because the original P2S runs did not retain the required metric-time trajectory.

## 12. Artifact preservation checklist

For each run preserve:

```text
config TOML used
framework version + git commit
OpenAPI document used for compilation
baseline primitive trace
compiled trace + OCLI catalog
golden/silver JSONL
checkpoint/run metadata
model identifier and serving endpoint
state-reset configuration
patch results / target revision
post-hoc verification outputs
coverage raw data + CSV where applicable
wall-clock start/end
SHA-256 manifest
```

The aim is not merely that a command can be rerun; it is that another researcher can identify **which target state, interface contract, model, reset primitive, and measurement definition produced every reported value**.
