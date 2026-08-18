# Track A Reproduction with P2S Framework v1.2

This document replaces the primary dependence on the historical SEAL `proxy.py`, `trace_compiler.py`, and `eval_student_p2s_engine.py`. Those files remain in `original_reporducibility_docs/` only as an audit record. The v1.2 workflow uses the public P2S package for trace capture, compilation, state orchestration, and evaluation.

Track A contains two classes of experiment:

1. **P2S-family model comparison** on the same SEAL/HackathonBench trace: P2S fine-tuned Qwen3.5-9B, untuned Qwen3.5-9B, DeepSeek-V4-Flash.
2. **Independent black-box baselines**: AutoRestTest, CATS, Schemathesis. P2S prepares a fair/stable target contract and credential, but does not replace these tools.

## 1. Target checkout and base environment

Use the retained SEAL evaluation branch:

```bash
git clone https://github.com/triet2809/SWP391_SealHackathon_BackEnd.git
cd SWP391_SealHackathon_BackEnd
git switch be-10/07
export SEAL_ROOT="$PWD"
```

The historical Windows environment used Java 17, Maven, PostgreSQL, Node where required, Git Bash, and a Python virtual environment with `psycopg2-binary`, HTTP/model dependencies, and P2S.

Install the framework into that environment or another environment that can invoke OCLI and PostgreSQL tooling:

```bash
pip install /path/to/p2s_framework-1.2.0-py3-none-any.whl
npm install -g openapi-to-cli
```

## 2. Build the clean SEAL database

The retained database initialization order is:

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

Build a standalone JAR so the target is decoupled from IDE/integrated-terminal lifecycle events:

```bash
mvn clean package -DskipTests

java -jar target/seal-hackathon-backend-0.0.1-SNAPSHOT.jar \
  --spring.datasource.url=jdbc:postgresql://localhost:5432/seal_hackathon \
  --spring.datasource.username=postgres \
  --spring.datasource.password=postgres \
  --app.security.jwt.secret="${SEAL_JWT_SECRET}"
```

Use a disposable research-only JWT secret; do not publish production credentials.

Verify:

```bash
curl -s http://localhost:8080/api/v3/api-docs >/dev/null
```

## 3. Record one shared Track-A trace with the P2S proxy

Use the fine-tuned config for the capture stage; the captured trace can then be copied/reused for the model controls.

```bash
CFG=configs/research/track_a_seal_p2s.toml
RUN=runs/track-a/shared

p2s prepare --config "$CFG" --workdir "$RUN"
```

`prepare` fetches the fresh OpenAPI document and obtains the controlled Coordinator token after the configured role/UUID normalization.

### Terminal 1 — proxy

```bash
p2s proxy --config "$CFG" --workdir "$RUN"
```

The v1.2 proxy:

- listens on `8090`;
- forwards to `http://localhost:8080`;
- uses the explicit `X-Flow-ID` injected by the SEAL flow suite;
- maintains a thread-safe counter per flow ID;
- masks Authorization/Cookie/signature values in the persisted trace;
- skips health-check traffic.

### Terminal 2 — record workload

```bash
p2s record --config "$CFG" --workdir "$RUN"
```

The configured workload calls:

```bash
BASE_URL=http://localhost:8090/api bash seal-simulations/seal-flows/seal_flows.sh
```

The suite consists of the 20 business-flow functions plus the one-time Coordinator bootstrap flow, producing the 21-flow evaluation corpus used in the paper.

The frozen trace is:

```text
runs/track-a/shared/baseline_primitive_traces.jsonl
```

## 4. Compile with the shared v1.2 compiler

```bash
p2s compile --config "$CFG" --workdir "$RUN"
```

The compiler handles the SEAL-specific `/api` context prefix through `context_path_prefix = "/api"`; it no longer requires a private SEAL compiler file.

Before evaluation, v1.2 creates a runtime copy of the OpenAPI document and relaxes non-path `required` constraints. Path parameters stay required. This retains the omission-testing behavior that the historical evaluator implemented by patching OCLI's cached spec.

## 5. Reproduce the P2S fine-tuned run

Serve the fine-tuned Q8_0 model at:

```text
http://localhost:8081/v1
```

Then:

```bash
p2s fuzz \
  --config configs/research/track_a_seal_p2s.toml \
  --workdir runs/track-a/p2s-ft
```

If the compiled trace was created in a shared directory, copy the frozen trace and compiled artifacts into each run directory before `fuzz`, or compile separately from the same frozen primitive trace.

### State behavior encoded in v1.2

The SEAL config uses the PostgreSQL template adapter:

- active DB: `seal_hackathon`;
- template DB: `seal_hackathon_snap`;
- seed: baseline SQL plus all three gap-fill migrations;
- fixed test Coordinator normalization after seed;
- template snapshot for mutation isolation;
- historical incremental prefix behavior (`pre_step_replay = "last"`);
- six attempts per target step.

This behavior is implemented once in `p2s.engine` / `p2s.engine.adapters`, not in a SEAL-only evaluator.

## 6. Untuned Qwen control

Use the identical target, trace, compiler, taxonomy, reset path, and P2S evaluator. Only the LLM backend changes.

Serve the untuned architecture-matched Qwen3.5-9B endpoint at `http://localhost:1234/v1`, then:

```bash
p2s fuzz \
  --config configs/research/track_a_seal_base_qwen.toml \
  --workdir runs/track-a/base-qwen
```

The config writes separate Golden/Silver/checkpoint artifacts so model runs cannot overwrite one another.

## 7. DeepSeek control

```bash
export DEEPSEEK_API_KEY='<your-key>'

p2s fuzz \
  --config configs/research/track_a_seal_deepseek.toml \
  --workdir runs/track-a/deepseek
```

The model identifier is:

```text
deepseek-v4-flash
```

## 8. Candidate versus verified outcome

The framework's engine Golden labels are **candidate labels**, not automatic vulnerability claims. Track-A headline outcomes require the post-hoc semantic verifier.

At minimum the verification stage must reject:

- `--help` / `-h` CLI-help bleed;
- pseudo mass-assignment fields ignored by Jackson/backend binding;
- legitimate authorized `200/201` responses with no actual identity/resource/token mutation.

Then deduplicate accepted results by a documented endpoint/status/response-error signature and keep server faults separate from verified authorization/business-state bypasses.

The primary v1.2 verifier is available directly from the framework. For example:

```bash
p2s verify \
  --golden-file runs/track-a/p2s-ft/p2s_ft_golden_dataset.jsonl \
  --verified-out runs/track-a/p2s-ft/p2s_ft_verified_goldens.jsonl

p2s verify \
  --golden-file runs/track-a/base-qwen/base_qwen_golden_dataset.jsonl \
  --verified-out runs/track-a/base-qwen/base_qwen_verified_goldens.jsonl

p2s verify \
  --golden-file runs/track-a/deepseek/deepseek_golden_dataset.jsonl \
  --verified-out runs/track-a/deepseek/deepseek_verified_goldens.jsonl
```

If you run the optional local SLM attack-vector reclassifier, treat it as taxonomy cleanup only; it must not promote a candidate into a verified vulnerability.

The final paper audit target is:

| Model | Executed records | Candidate Goldens | Validated outcomes | Unique validated signatures |
|---|---:|---:|---:|---:|
| P2S fine-tuned | 1,075 | 48 | 31 | 30 |
| DeepSeek-V4-Flash | 1,094 | 29 | 26 | 26 |
| Base Qwen3.5-9B | 1,122 | 21 | 16 | 16 |

These are retained-run audit targets, not acceptance criteria for a fresh stochastic run.

## 9. Prepare the shared target for conventional baselines

Config:

```text
configs/research/track_a_baselines.toml
```

### Step 9.1 — patch the long-lived test JWT **before rebuild**

```bash
p2s patch \
  --config configs/research/track_a_baselines.toml \
  --workdir runs/track-a/baseline-prep
```

This idempotently patches the retained SEAL source to use:

```text
access-token expiration = 525,600 minutes (one year)
```

in both the application properties default and JWT expiration calculation. This is necessary because the AutoRestTest run lasts five hours.

Rebuild/relaunch SEAL after the patch:

```bash
./mvnw clean spring-boot:run
```

or rebuild the standalone JAR and launch it as above.

### Step 9.2 — fetch one sanitized OpenAPI contract

```bash
p2s fetch-openapi \
  --config configs/research/track_a_baselines.toml \
  --workdir runs/track-a/baseline-prep
```

The framework performs the historical equalisation:

- server URL becomes `http://localhost:8080/api`;
- `/auth/logout` is removed;
- `DELETE /users/{id}` is removed;
- `DELETE /users/me` is removed.

No producer/consumer dependency hints or business-state answers are injected.

### Step 9.3 — fresh Coordinator token

```bash
p2s auth \
  --config configs/research/track_a_baselines.toml \
  --workdir runs/track-a/baseline-prep
```

The config first truncates `revoked_tokens`, then logs in as the controlled Coordinator identity and saves the token to:

```text
$SEAL_ROOT/.p2s/seal_baseline_coordinator_token.txt
```

Do not restart the backend after obtaining this token unless you intentionally reacquire a fresh token afterward.

## 10. AutoRestTest — final experiment parity

**Resolved source-of-truth point:** the completed original AutoRestTest experiment used **DeepSeek-V4-Flash**. The older local-base-Qwen TOML/header in an archival setup note is not the final-run model configuration.

Use the AutoRestTest repository/revision preserved for the experiment. The historical Windows/Python 3.12 setup required:

```bash
python -m venv venv
source venv/Scripts/activate
python -m pip install --upgrade pip setuptools wheel
sed -i 's/<3.11/<3.13/g' pyproject.toml
sed -i 's/==/>=/g' requirements.txt
sed -i '/^python>=/d; /^pip>=/d; /^setuptools>=/d; /^wheel>=/d' requirements.txt
pip install -r requirements.txt
pip install -e . --no-deps
export PYTHONPATH="$(pwd)/src"
```

If the exact published AutoRestTest revision already supports your Python version, pin that revision and avoid gratuitous compatibility edits.

### Historical socket-safety patch

The completed Windows run inserted:

```python
time.sleep(0.015)
```

in the request-dispatch path to avoid ephemeral-port exhaustion. Apply the retained patch to the retained AutoRestTest revision rather than blindly text-replacing a different upstream version.

### Required configuration controls

Use the P2S-prepared sanitized `seal_baseline_openapi.json` and fresh Coordinator token. The completed run settings are:

```text
strict_validation = false
Header Agent      = disabled
cached graph       = false
cached Q-table     = false
max_combinations   = 12
max_total_combinations = 3000
base_samples_per_size = 200
combination_seed   = 42
Value-agent workers = 2
Q-learning alpha   = 0.1
discount_factor    = 0.9
max_exploration    = 1.0
mutation_rate      = 0.2
time_duration      = 18,000 seconds
LLM                = DeepSeek-V4-Flash
```

Configure the AutoRestTest provider fields for DeepSeek-V4-Flash and inject the bearer token through `[custom_headers]` without committing secrets.

Run:

```bash
python -m autoresttest.autoresttest --skip-wizard
```

Preserve the entire `data/seal_openapi/` directory, especially `server_errors.json`, graph/table state, configuration, and run logs.

Native error counters are not automatically verified deep/stateful security outcomes. Keep the paper's post-hoc interpretation layer separate.

## 11. CATS

Use the same sanitized OpenAPI file and same stable Coordinator access conditions.

```bash
COORD_TOKEN=$(cat "$SEAL_ROOT/.p2s/seal_baseline_coordinator_token.txt")

./cats.exe \
  --contract "$SEAL_ROOT/seal_baseline_openapi.json" \
  --server http://localhost:8080/api \
  -H "Authorization=Bearer ${COORD_TOKEN}" \
  --output cats_report
```

Pin/publish the actual CATS version used for a reproduction; do not rely indefinitely on a `latest` download URL.

Preserve every JSON test artifact in `cats_report/`. The post-hoc audit should inspect bodies/operations, not only dashboard totals. In particular, an IDOR-themed HTTP 200 is not a disclosure unless the response proves unauthorized data/action.

## 12. Schemathesis

```bash
pip install "schemathesis[all]"
COORD_TOKEN=$(cat "$SEAL_ROOT/.p2s/seal_baseline_coordinator_token.txt")

schemathesis run "$SEAL_ROOT/seal_baseline_openapi.json" \
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
.schemathesis/  # if produced by the installed version
```

The retained report had generic catch-all 500 bodies whose underlying exception class was not observable from the report. Preserve that epistemic boundary rather than assigning a specific root cause without evidence.

## 13. Track-A artifact layout

```text
runs/track-a/
├── shared/
│   ├── baseline_primitive_traces.jsonl
│   ├── compiled_traces.jsonl
│   └── ocli_catalog.json
├── p2s-ft/
├── base-qwen/
├── deepseek/
└── baseline-prep/

$SEAL_ROOT/
├── seal_baseline_openapi.json
└── .p2s/
    └── seal_baseline_coordinator_token.txt   # private; do not publish
```

For public artifacts, replace real tokens/secrets with placeholders and publish hashes/manifests for the non-secret inputs and outputs.
