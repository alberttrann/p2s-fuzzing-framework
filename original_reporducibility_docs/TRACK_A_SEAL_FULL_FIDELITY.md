# P2S Track A — Full-Fidelity SEAL / HackathonBench Reproduction

**Companion to P2S Framework v1.1.0**  
**Purpose:** preserve the implementation-critical Track-A experiment procedure from the three archived notes: the SEAL P2S guide, the AutoRestTest guide, and the CATS/Schemathesis guide.

> **Authorized local testing only.** The procedure assumes an isolated local research backend and resettable test databases under the experimenter's control.

## 1. Preservation rule

Track A has four distinct executions and they should not be flattened into one generic recipe:

1. **P2S fine-tuned Qwen3.5-9B evaluation on SEAL**;
2. **architecture-matched untuned Qwen3.5-9B and DeepSeek controls through the same P2S harness**;
3. **AutoRestTest conventional baseline**;
4. **CATS and Schemathesis conventional baselines**.

For maximum fidelity, use this priority:

1. retained final paper / completed run artifacts for *what was actually reported*;
2. retained target branch and archived scripts for exact execution behavior;
3. the user-supplied `.txt` notes for environment workarounds and post-hoc procedures;
4. the normalized `p2s` SDK only for new targets/new repetitions where historical parity is not required.

The release includes `docs/track_a_helpers/` so critical historical implementation details are inspectable rather than summarized away.

## 2. Discrepancy ledger — preserve, but do not blindly reproduce stale text

| Topic | Archived note | Final-parity treatment |
|---|---|---|
| AutoRestTest value model | Early guide says local base Qwen3.5-9B | Completed run log is authoritative: **DeepSeek-V4-Flash** |
| AutoRestTest qualitative classifier | Early heuristic sends unmatched records to `Deep Business Logic Error` | Keep as exploratory history only; final artifact audit relies on directly observable fields, especially null/empty parameter maps |
| Schemathesis generic 500 | Old parser categories can suggest a root cause | Preserve 68 raw 5xx artifacts, but the generic catch-all body does **not** expose the underlying exception class |
| P2S candidate goldens | Engine labels 48/29/21 candidates | Security claims use post-hoc validated 31/26/16 outcomes; candidate depth/vector tables remain candidate-level |
| Credentials / API keys | Historical notes may contain literal local credentials/provider keys | Local test-account defaults may be parameterized; third-party API keys are **not republished** |

---

# Part A — P2S Track-A evaluation on the SEAL backend

## 3. Host environment retained by the original Windows run

The archived SEAL guide assumes Windows + Git Bash with Java 17, Node.js, Docker Desktop/WSL2, PostgreSQL client tools, Maven, and Python. A matching environment is preferable when reproducing Windows-specific evaluator behavior.

Representative Git-Bash setup:

```bash
export JAVA_HOME="/c/Program Files/Eclipse Adoptium/jdk-17.0.19.10-hotspot"
export PATH="$JAVA_HOME/bin":"/c/Program Files/nodejs":"/c/Program Files/Docker/Docker/resources/bin":"/c/Program Files/PostgreSQL/17/bin":"/c/ProgramData/chocolatey/bin":$PATH

python -m venv venv
source venv/Scripts/activate
python -m pip install --upgrade pip
pip install psycopg2-binary transformers torch requests safetensors openai anthropic
```

Record exact JDK/Python/PyTorch/Transformers/Safetensors versions in the reproduction manifest; the archived evaluator contains Windows/Qwen compatibility patches whose necessity can be version-dependent.

## 4. Recreate the SEAL database exactly

`DROP DATABASE` and `CREATE DATABASE` are separate autocommit operations:

```bash
psql "postgresql://postgres:postgres@localhost:5432/postgres" -c "DROP DATABASE IF EXISTS seal_hackathon;"
psql "postgresql://postgres:postgres@localhost:5432/postgres" -c "CREATE DATABASE seal_hackathon;"
psql "postgresql://postgres:postgres@localhost:5432/seal_hackathon" -f seal_hackathon_full_2026-07-04.sql
psql "postgresql://postgres:postgres@localhost:5432/seal_hackathon" <<'SQL'
\i migration_gapfill.sql
\i migration_gapfill2.sql
\i migration_gapfill3.sql
SQL
```

Preserve the SQL dump and all three gap-fill migrations in the published target artifact.

## 5. Build and launch the backend as a standalone JAR

The source note explicitly avoids keeping `mvn spring-boot:run` attached to an IDE terminal because a false EOF could shut down the backend.

```bash
mvn clean package -DskipTests

java -jar target/seal-hackathon-backend-0.0.1-SNAPSHOT.jar \
  --spring.datasource.url=jdbc:postgresql://localhost:5432/seal_hackathon \
  --spring.datasource.username=postgres \
  --spring.datasource.password=postgres \
  --app.security.jwt.secret="$SEAL_JWT_SECRET"
```

Use a fixed **test-only** signing secret for the complete run. Do not restart the backend between obtaining a long-lived baseline token and launching the baseline unless a new token is fetched afterward.

Verify:

```bash
curl -s http://localhost:8080/api/v3/api-docs -o seal_openapi.json
```

## 6. Record the 21 stateful flows through the historical proxy

The SEAL flow suite shares authenticated identities across flow boundaries, so the AITasker reset-on-login heuristic is not sufficient. The retained proxy uses explicit `X-Flow-ID` headers and a thread-safe per-flow step counter.

Use the included helper:

```bash
python docs/track_a_helpers/proxy_seal_historical.py
```

The parity proxy must retain these invariants:

- listen on `0.0.0.0:8090` and forward to `http://localhost:8080`;
- read `X-Flow-ID` and keep a separate atomic step counter per flow;
- reset a flow's step counter on `POST /api/auth/register` for that flow ID;
- strip hop-by-hop headers and the internal `X-Flow-ID` before forwarding;
- skip `/health`, `/api/health`, and `/actuator/health` from trace output;
- persist request/response body + ordering to `primitive_traces.jsonl`;
- mask `Authorization`, `Cookie`, and signature-like sensitive headers in the stored trace.

Run the archived flow driver through the proxy:

```bash
export SEAL_COORD_PASSWORD="<local coordinator password>"
export SEAL_USER_PASSWORD="<local test-user password>"
BASE_URL=http://localhost:8090/api bash docs/track_a_helpers/seal_flows_historical.sh
```

The flow driver encodes business rules that are part of successful state construction, including lowercase role/enum values, globally unique criteria-template names, and the minimum team-size rule before registration closure. Do not simplify the flow script into independent endpoint probes.

## 7. Compile the primitive trace with the SEAL-specific compiler

Historical parity:

```bash
curl -s http://localhost:8080/api/v3/api-docs -o swagger.json
python docs/track_a_helpers/trace_compiler_seal_historical.py
```

The archived compiler includes four behaviorally important details:

1. strip Spring's `/api` context prefix before route matching;
2. skip paths containing `//` after prefix stripping, because they indicate an unset path variable in the trace driver;
3. preserve OCLI command naming rules exactly, including method suffix only when a path exposes multiple HTTP methods;
4. resolve a single-level OpenAPI `$ref` for query-parameter types so Spring `Pageable`/object parameters are represented as objects rather than silently defaulting to strings.

Expected artifacts:

```text
primitive_traces.jsonl
compiled_traces.jsonl
seal_ocli_catalog.json
```

Register the OCLI profile:

```bash
ocli profiles add seal \
  --api-base-url http://localhost:8080/api \
  --openapi-spec http://localhost:8080/api/v3/api-docs \
  --api-bearer-token "" \
  --command-prefix ""
ocli use seal
```

## 8. Historical evaluator parity — do not replace with only `p2s fuzz`

For the reported artifacts, run the included sanitized archival evaluator:

```bash
python docs/track_a_helpers/eval_student_p2s_engine_historical_sanitized.py
```

The normalized SDK remains useful for new experiments, but the historical evaluator carries additional final-run behavior that materially affects parity.

### 8.1 Backend selection and separate output prefixes

The archived evaluator supports:

```text
transformers
llamacpp
lm_studio
openai
anthropic
```

For the three paper runs, preserve the same traces/catalog/state-reset path and change only the model backend:

- fine-tuned Qwen3.5-9B Q8_0 through `llama-server` at `http://localhost:8081/v1`;
- untuned Qwen3.5-9B Q8_0 through the retained LM Studio/OpenAI-compatible endpoint;
- DeepSeek-V4-Flash through its provider endpoint.

Never reuse the same output prefix across models. The runner derives `<backend>_golden_dataset.jsonl`, `<backend>_silver_dataset.jsonl`, `<backend>_processed_flows.txt`, `<backend>_execution_log.txt`, and `<backend>_run_metadata.json`.

### 8.2 Windows/Qwen runtime patches retained in the evaluator

The archived final evaluator applies two compatibility families before model initialization:

- PyTorch initialization bypasses for integer tensors (`uint8`/`int8`), preventing unsupported normal initialization on quantized tensors;
- Safetensors key remapping for the historical double-prefix form `model.language_model.language_model.*`.

These patches are not claimed to be universally necessary. They are preserved because they were part of the final Windows evaluator. If a newer stack no longer requires them, document the changed versions rather than silently deleting the difference from a parity run.

### 8.3 Generation and parser settings

Retained evaluator behavior includes:

```text
MAX_ATTEMPTS = 6
max generation tokens = 24,576
local OpenAI-compatible thinking budget = 8,192
OpenAI-compatible HTTP timeout = 200 s
OCLI execution timeout = 150 s
temperature = 0.1 on attempt 1, then rises by 0.15/attempt up to 0.8
```

The response parser accepts the fine-tuned fenced-command form, strict/loose JSON used by external/base models, and a `<think>` + bare-OCLI fallback. Preserve this multi-format parser when reproducing the reported M1/M2/M3 artifacts.

### 8.4 OCLI command normalization retained in the evaluator

Before execution, the archived runner performs compatibility handling that the concise reproducibility guide previously hid:

- deep-unescapes double/triple escaped quotes;
- expands selected model-produced shell expressions into literal values;
- re-tokenizes OCLI flags;
- normalizes OpenAPI object query parameters such as `--p` / `--pageable` into JSON-object values;
- caps extreme flag values and transfers oversized content through environment variables;
- strips model-injected `--profile` / `-p` profile selectors;
- refreshes the controlled Coordinator bearer token and appends the `seal` profile;
- converts literal NUL to escaped `\\x00`;
- on Windows, executes through a temporary Git-Bash script when Git Bash is available.

These are evaluation-harness robustness controls. They should be recorded because changing them changes the observed CLI-syntax failure distribution.

### 8.5 OCLI profile auto-registration and OpenAPI relaxation

At startup the archived evaluator scans local/global OCLI profiles, registers `seal` if missing, and selects it. It then hot-patches the cached OCLI OpenAPI document by relaxing non-path `required=true` parameters and recursively removing schema `required` lists.

This step is especially important for parity because it intentionally allows **Mandatory Omission** and other negative tests to reach OCLI/backend handling rather than being blocked solely by client-side schema enforcement. Do not omit it from a historical rerun.

### 8.6 PostgreSQL snapshot protocol

The final evaluator uses:

```text
active DB   = seal_hackathon
template DB = seal_hackathon_snap
```

Snapshot creation/restoration temporarily disables new connections, terminates active clients, retries creation/restoration up to five times, re-enables connections, and waits for the backend to reconnect. Preserve this behavior rather than replacing it with an unverified faster reset.

## 9. Post-hoc semantic validation is mandatory

Engine candidate labels are not the final security claims. Run:

```bash
python docs/track_a_helpers/validate_seal_goldens.py \
  --golden-file llamacpp_golden_dataset.jsonl \
  --output-verified llamacpp_verified_goldens.jsonl

python docs/track_a_helpers/deduplicate_goldens.py llamacpp_verified_goldens.jsonl
python docs/track_a_helpers/reclassify_vectors.py llamacpp both
```

Repeat with the correct prefixes for the other model runs.

The retained validator explicitly removes at least:

- CLI `--help` / `-h` bleed that exits without an API request;
- Jackson-ignored pseudo mass-assignment flags that never bind to state;
- normal authorized `200/201` calls where no resource identity or credential actually changed.

Deduplication groups by endpoint, observed status, and extracted response/error signature. Attack-vector reclassification is a separate diagnostic step; do not use it to upgrade a candidate into a verified vulnerability.

The final aggregate audit target is:

| Metric | P2S FT | DeepSeek | Base Qwen |
|---|---:|---:|---:|
| Executed records | 1,075 | 1,094 | 1,122 |
| Candidate goldens | 48 | 29 | 21 |
| Validated outcomes | 31 | 26 | 16 |
| Verified 500 server faults | 24 | 23 | 13 |
| Verified security bypasses | 7 | 3 | 3 |
| Unique validated signatures | 30 | 26 | 16 |
| M1 syntax pass | 99.9% | 95.8% | 99.4% |
| M2 silver exact/class | 56.2% / 82.1% | 15.1% / 68.9% | 29.6% / 79.3% |

These are comparison targets for the retained run, not values a fresh stochastic rerun must be forced to match.

---

# Part B — AutoRestTest Track-A baseline

## 10. Baseline target equalization is normative

AutoRestTest, CATS, and Schemathesis use the same fresh live OpenAPI document and a fresh long-lived Coordinator token. They do **not** receive hand-written producer-consumer links, resource IDs, state ordering, or hidden flow annotations.

### 10.1 Extend SEAL access-token lifetime to one year

The original baseline note patches both the application default and the explicit JWT expiry calculation:

```java
// AppProperties.java
private int accessTokenExpirationMinutes = 525600;

// JwtService.java
Instant exp = now.plus(525600, ChronoUnit.MINUTES);
```

Then clean-rebuild/relaunch the backend before obtaining the baseline token:

```bash
./mvnw clean spring-boot:run
```

If the branch exposes the value through configuration instead, set the equivalent test-only value:

```yaml
app:
  security:
    jwt:
      access-token-expiration-minutes: 525600
```

### 10.2 Verify token lifetime against the currently running backend

```bash
SEAL_COORD_PASSWORD="<local password>" \
python docs/track_a_helpers/verify_long_lived_jwt.py
```

Do not assume the patch took effect. The archived notes explicitly verify `exp` and expect roughly 364 remaining days after issuance.

### 10.3 Keep the signing secret stable for the complete baseline run

A token signed by an earlier backend instance can fail after a restart if the active JWT secret changed. Therefore:

1. use a fixed test-only JWT signing secret;
2. start/restart SEAL;
3. clear `revoked_tokens`;
4. obtain a fresh token from **that running process**;
5. write that token into the baseline config;
6. do not restart SEAL afterward without obtaining another token.

## 11. AutoRestTest compatibility environment

The archived Windows/Python-3.12 setup used:

```bash
git clone https://github.com/selab-gatech/autoresttest.git
cd autoresttest
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

Those edits are historical compatibility patches, not timeless project requirements. Pin the AutoRestTest commit/revision in a strict reproduction and only apply the patches when they match that revision.

## 12. Shared OpenAPI sanitization and fresh token

```bash
curl -s http://localhost:8080/api/v3/api-docs -o seal_openapi.json
python /path/to/p2s/source/docs/track_a_helpers/sanitize_baseline_openapi.py seal_openapi.json
```

The sanitizer:

- fixes `servers` to `http://localhost:8080/api`;
- removes `/auth/logout`;
- removes self-deletion operations under `/users/{id}` and `/users/me`.

Then clear stale revocations and obtain a new Coordinator token from the active backend. Preserve the resulting token only in local run configuration, never in the repository.

## 13. AutoRestTest final-run configuration

The reported run uses:

```text
spec                    seal_openapi.json
strict_validation       false
Header Agent            disabled
cached graph             false
cached table             false
request duration         18,000 s
Windows dispatcher       15 ms delay
Authorization            fresh long-lived Coordinator Bearer JWT
completed-run value LLM  DeepSeek-V4-Flash
```

The archived note's local-base-Qwen `[llm]` template is retained as historical setup evidence, but **must not override the completed run log** when reproducing the paper result.

Other retained control values:

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

Use provider credentials only from environment/local secret storage.

## 14. Windows socket-safety patch

The historical run inserted a 15 ms delay into AutoRestTest's request dispatcher because the unthrottled Windows loop exhausted ephemeral ports.

The source note's patch concept is:

```python
def dispatch_request(*args, **kwargs):
    time.sleep(0.015)
    return _real_dispatch_request(*args, **kwargs)
```

Apply this only to the matching archived revision. On a newer revision, port the behavior deliberately rather than using a blind text replacement.

## 15. Execute AutoRestTest and preserve the full native artifact

```bash
python -m autoresttest.autoresttest --skip-wizard
```

Expected shape:

1. Q-table/value-table generation;
2. five-hour MARL request-generation phase.

Preserve the complete `data/seal_openapi/` directory, configuration, graph/Q-table files, terminal log, and especially:

```text
data/seal_openapi/server_errors.json
```

The retained completed-run native counters are useful **audit targets**, not vulnerability counts:

```text
Total requests                  806,955
Requests/s                      44.8
Successful operations           87 / 127 (68.5%)
HTTP 500 responses              222,802
Native "unique server errors"   91,188
Persisted server_errors records 2,304
```

The dashboard's 91,188 counter and the 2,304 persisted records are different accounting layers and must remain separately named.

## 16. AutoRestTest post-hoc audit

Run the included direct-artifact audit:

```bash
python /path/to/p2s/source/docs/track_a_helpers/autoresttest_posthoc_audit.py \
  --server-errors data/seal_openapi/server_errors.json
```

This preserves the source note's strongest directly observable check: count the persisted records and determine how many expose null/empty parameter maps, plus an operation-by-operation breakdown.

The earlier regex/keyword classifier is preserved in the historical note but should **not** be treated as ground truth because unmatched records fall through to a residual category. Do not translate that residual bucket into "deep business logic vulnerabilities."

---

# Part C — CATS baseline

## 17. Acquire and pin CATS

The historical Windows note downloaded the latest Endava Windows release and extracted `cats.exe`. For a reproducible artifact, record the exact CATS version/release digest rather than allowing `latest` to drift.

Verify the binary before use:

```bash
ls -lh cats.exe
```

## 18. Reuse the same baseline-favourable target preparation

CATS uses the same:

```text
seal_openapi.json
http://localhost:8080/api
fresh long-lived Coordinator JWT
```

Use the same sanitization described above, clear `revoked_tokens`, and fetch a fresh token from the currently running backend. The original note stored it in `cats_jwt.txt` for local use.

## 19. Execute CATS

```bash
COORD_TOKEN=$(cat cats_jwt.txt)

./cats.exe \
  --contract seal_openapi.json \
  --server http://localhost:8080/api \
  -H "Authorization=Bearer ${COORD_TOKEN}" \
  --output cats_report
```

Preserve the complete `cats_report/` directory, not only the dashboard total.

---

# Part D — Schemathesis baseline

## 20. Install and execute

```bash
source venv/Scripts/activate
pip install "schemathesis[all]"

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
.schemathesis/        # if created by that version
```

---

# Part E — CATS + Schemathesis post-hoc evidence

## 21. Run the source-derived artifact parser

```bash
python /path/to/p2s/source/docs/track_a_helpers/cats_schemathesis_posthoc_audit.py
```

The parser preserves the original experimental checks:

- enumerate CATS fuzzers associated with 5xx artifacts;
- group CATS 5xx artifacts by broad fuzzer family;
- inspect SQL-injection-themed 5xx bodies for visible PostgreSQL/Hibernate syntax-exception markers;
- separately enumerate IDOR-themed requests and inspect all HTTP-200 response bodies before any disclosure claim;
- parse Schemathesis JUnit 5xx failures and summarize the visible response body.

Interpretation boundaries are mandatory:

- a CATS IDOR-themed HTTP 200 is not automatically a data leak; the retained audit found the inspected 200 bodies were empty arrays;
- absence of visible SQL exception markers means only that the supplied response artifact does not expose such an exception, not that a request is proven never to have reached the database;
- Schemathesis's generic `{"message":"An unexpected error occurred"}` body does not reveal the underlying exception class;
- raw 5xx counts are robustness/server-fault evidence unless an additional semantic artifact demonstrates an authorization or lifecycle violation.

Retained comparison targets:

```text
CATS          45,781 tests; 9,370 dashboard 5xx; no audited deep/stateful security outcome
Schemathesis  10,851 cases; 68 JUnit 5xx; generic catch-all response, root cause not observable
```

---

# Part F — Track-A parity checklist

## 22. Before accepting a run as comparable

- [ ] SEAL DB rebuilt from the retained dump + all three migrations.
- [ ] Backend runs with a stable test JWT secret.
- [ ] P2S trace capture uses the header-tagged proxy and full 21-flow driver.
- [ ] SEAL trace compiler applies `/api` stripping, malformed-`//` skip, and richer query-type/catalog logic.
- [ ] P2S historical evaluator retains OCLI auto-profile setup, required-constraint relaxation, DB snapshot protocol, parser/timeout/normalization fixes, and separate output prefixes.
- [ ] Three model runs change only the model backend while reusing the same traces/catalog/evaluator path.
- [ ] Candidate goldens are post-hoc validated before security claims.
- [ ] Baselines use a 525,600-minute token lifetime and a token minted by the currently running backend.
- [ ] `/auth/logout` and self-deletion operations are removed from the baseline contract.
- [ ] AutoRestTest uses `strict_validation=false`, disabled Header Agent, fresh caches, the 15 ms Windows throttle, and 18,000-second request generation.
- [ ] AutoRestTest completed-run model is recorded as DeepSeek-V4-Flash for paper parity.
- [ ] CATS and Schemathesis reuse the same sanitized contract and fresh Coordinator token.
- [ ] Native baseline counters remain distinct from independently verified semantic outcomes.
- [ ] Exact tool commits/releases, model revisions, hashes, and runtime versions are recorded in the artifact manifest.

## 23. Helper provenance and security hygiene

`docs/track_a_helpers/` contains code extracted from the user-supplied Track-A notes. The evaluator copy is intentionally named `historical_sanitized`: any literal third-party API-key default has been removed and must be supplied through environment variables. This is a security-hygiene change, not an experimental-method change.
