# Track B: 11 RESTgym Services with P2S Framework v1.2

This is the framework-native Track-B protocol. It preserves the service-specific **Phase-1 patches, authentication/proxy behavior, context paths, and reset primitives** discovered in the original experiments, but replaces the old shared `trace_compiler.py` and `eval_student_p2s_engine.py` research wrappers with the public P2S v1.2 compiler/fuzzer/lifecycle.

## 1. Why Track B does not put the P2S proxy on port 9090

RESTgym itself already provides a semantically active mitmproxy on host port `9090`. Depending on the service, that layer performs authentication/session handling or request rewriting. ERC20 is the clearest example: the proxy rewrites the dummy contract address in requests to the **freshly deployed Ganache contract address**.

Therefore the v1.2 framework-native topology is intentionally:

```text
retained workload fixture
        |
        v
RESTgym mitmproxy :9090  ----> service runtime :8080/internal stack
        |
        +---- fixture writes P2S primitive-trace JSONL
                      |
                      v
                p2s record (freeze)
                      |
                      v
                p2s compile
                      |
                      v
                p2s fuzz -- shared v1.2 engine
```

The optional `[proxy]` section in Track-B TOMLs listens on `9190` only for diagnostics. **Do not start it for the retained Track-B reproduction.**

This design removes the need for a Track-B-specific P2S proxy/compiler/evaluator while preserving RESTgym's native instrumentation/auth layer exactly where it matters.

## 2. Common setup

```bash
git clone https://github.com/restgym/restgym.git
cd restgym
export RESTGYM_ROOT="$PWD"

python -m venv venv
source venv/Scripts/activate

pip install --only-binary=:all: "zstandard>=0.22.0"
pip install --prefer-binary -r src/requirements.txt
pip install /path/to/p2s_framework-1.2.0-py3-none-any.whl
npm install -g openapi-to-cli
```

On Windows/Git Bash, retain the original normalization as needed:

```bash
export MSYS_NO_PATHCONV=1
export PYTHONUNBUFFERED=1
git config --global core.autocrlf input
find . -type f -name "*.sh" -exec sed -i 's/\r$//' {} +
```

Serve the P2S fine-tuned Q8_0 model at:

```text
http://localhost:8081/v1
```

## 3. Common per-service command sequence

For each service:

```bash
CFG=configs/research/track_b/<service>.toml
RUN=runs/track-b/<service>

p2s doctor  --config "$CFG" --workdir "$RUN"
p2s prepare --config "$CFG" --workdir "$RUN"
p2s record  --config "$CFG" --workdir "$RUN"
p2s compile --config "$CFG" --workdir "$RUN"
p2s fuzz    --config "$CFG" --workdir "$RUN"
```

`p2s fuzz` receives from TOML:

```text
time_budget_seconds = 3600
cyclic = true
clear_checkpoint_for_cyclic = true
reset_before_each_target = true
pre_step_replay = "none"
require_attack_flag_for_2xx = true
```

Thus the shared framework itself implements the old one-hour cyclic runner behavior.

After the run, preserve Golden/Silver JSONL and compute the **strict status-aligned 5xx-only FD proxy** with the shared framework:

```bash
p2s fd \
  --golden-file "$RUN/<service>_p2s_golden_dataset.jsonl" \
  --dedup-out "$RUN/<service>_strict_5xx_dedup.jsonl"
```

`p2s fd` filters status first and then deduplicates. Do not add Track-B 2xx security-intent candidates to SBFT FD.

## 4. Service 1 — blog

Config:

```text
configs/research/track_b/blog.toml
```

### Phase 1 — container

No special RESTgym enable patch was retained for blog.

```bash
p2s prepare --config configs/research/track_b/blog.toml --workdir runs/track-b/blog
```

This launches:

```text
restgym_blog
host 9090 -> RESTgym 9090
host 12345 -> JaCoCo agent
```

### Phase 2 — workload/trace

The retained `record_blog_full_52.py` is a **workload fixture**. It exercises all 52 documented operations through RESTgym `9090` and writes:

```text
p2s_traces/blog/primitive_traces.jsonl
```

`p2s record` runs it and freezes the result into the run directory.

### Phase 3+ — shared P2S

```bash
p2s compile --config configs/research/track_b/blog.toml --workdir runs/track-b/blog
p2s fuzz    --config configs/research/track_b/blog.toml --workdir runs/track-b/blog
```

### Reset contract

The framework command-state adapter executes the retained MySQL reseed:

```bash
docker exec -i restgym_blog mysql -ublog -pblog blogapi < apis/blog/database/blogapi.sql
```

## 5. Service 2 — ERC20

Config:

```text
configs/research/track_b/erc20.toml
```

### Phase 1 — mandatory Dockerfile patch

The retained image needs the logs directory created before Spring writes to it. `p2s prepare` applies the idempotent patch equivalent to:

```text
mkdir -p /results/$API/$TOOL/$RUN/code-coverage
```

becoming:

```text
mkdir -p /results/$API/$TOOL/$RUN/code-coverage /results/$API/$TOOL/$RUN/logs
```

The configured container launch also retains:

```text
--memory=6g
```

because the container combines Ganache, Spring/Web3j, and RESTgym/mitmproxy components.

### Proxy invariant

Do not bypass port `9090`. The RESTgym auth/proxy layer rewrites the dummy contract address to the contract deployed in the current Ganache state.

### Reset contract

Before each target the shared command adapter executes:

```bash
docker exec restgym_erc20 python3 /api/init-contract.py
```

The RESTgym proxy must remain active afterward so subsequent requests are rewritten to that newly deployed address.

### Shared P2S path

```bash
p2s prepare --config configs/research/track_b/erc20.toml --workdir runs/track-b/erc20
p2s record  --config configs/research/track_b/erc20.toml --workdir runs/track-b/erc20
p2s compile --config configs/research/track_b/erc20.toml --workdir runs/track-b/erc20
p2s fuzz    --config configs/research/track_b/erc20.toml --workdir runs/track-b/erc20
```

For JaCoCo reporting, use application classes rather than duplicate third-party/Lombok classes from the fat JAR; the historical workaround extracted `BOOT-INF/classes` before report generation.

## 6. Service 3 — features-service

Config:

```text
configs/research/track_b/features-service.toml
```

### Phase 1 — enable RESTgym before build

The retained configuration is disabled by default. `p2s prepare` writes:

```yaml
enabled: true
```

to:

```text
apis/features-service/restgym-api-config.yml
```

before building the image. This is mandatory because otherwise the RESTgym entrypoint can skip the intended mitmproxy path on `9090`.

### Form-urlencoded invariant

The `requires` / `excludes` constraint operations use:

```text
application/x-www-form-urlencoded
```

The v1.2 compiler handles form-urlencoded bodies directly; do not convert them to JSON merely to make compilation easier.

### Reset

```bash
docker restart restgym_features_service
```

Container restart restores the H2/in-memory baseline.

## 7. Service 4 — flight-search

Config:

```text
configs/research/track_b/flight-search.toml
```

### Phase 1 — auth patch before build

The retained RESTgym `auth.py` registers a normal user by default, which is insufficient for the protected airport/flight lifecycle. `p2s prepare` applies:

```text
"userType": "USER" -> "userType": "ADMIN"
```

and normalizes the test email when the expected old value is present.

The patch must happen **before Docker build**.

### Spec

The config copies the retained service specification from the running container into:

```text
p2s_specs/flightsearch.yaml
```

so the shared compiler uses the exact container contract.

### Reset

```bash
docker exec restgym_flightsearch mongosh flightdatabase --eval 'db.dropDatabase();'
docker exec restgym_flightsearch mongosh flightdatabase /api/database/init-mongo.js
```

## 8. Service 5 — gestao-hospital

Config:

```text
configs/research/track_b/gestao-hospital.toml
```

### Authentication invariant

Preserve RESTgym's session-cookie auto-authentication. The P2S OCLI endpoint remains RESTgym port `9090`; a direct unauthenticated request to the underlying Spring service is not equivalent.

### Reset

```bash
docker exec restgym_gestaohospital mongosh HospitalDB --eval 'db.dropDatabase();'
docker exec restgym_gestaohospital mongosh HospitalDB /api/database/init-mongo.js
```

This is the fast MongoDB drop/reseed adapter retained from the run.

## 9. Service 6 — kafka-rest-proxy

Config:

```text
configs/research/track_b/kafka-rest-proxy.toml
```

The service runs the Confluent Kafka REST stack. The original artifact selected a specification from the service's specification directory rather than preserving one canonical filename in the consolidated notes. v1.2 therefore does **not invent a filename**.

Set:

```bash
export P2S_KAFKA_SPEC='apis/kafka-rest-proxy/specifications/<exact-retained-file>.yaml'
```

The reset primitive deletes the target topic without restarting the full stack:

```bash
docker exec restgym_kafkarest kafka-topics \
  --bootstrap-server localhost:9092 \
  --delete --topic p2s-topic
```

For JaCoCo, report the Confluent application classes (for example `io/confluent/**`) rather than unrelated library code.

## 10. Service 7 — market

Config:

```text
configs/research/track_b/market.toml
```

### Phase 1

`p2s prepare` writes:

```yaml
enabled: true
```

before image build.

Preserve RESTgym's session-cookie authentication on port `9090`.

### Reset

```bash
docker restart restgym_market
```

The restart resets the H2/in-memory service state.

## 11. Service 8 — notebook-manager

Config:

```text
configs/research/track_b/notebook-manager.toml
```

### Phase 1

The service must be enabled before build:

```yaml
enabled: true
```

### Reset: explicit non-fabrication boundary

The paper/retained audit identifies the reset as **fast MySQL schema/data SQL re-import**, but the exact standalone shell command was not retained in a stable public form. v1.2 therefore requires an environment variable rather than silently substituting a slower/different restart:

```bash
export P2S_NOTEBOOK_RESET_COMMAND='<exact schema/data SQL re-import command from the retained branch>'
```

`p2s doctor` will report the missing reset command if it is not set.

This is intentional reproducibility behavior: a missing historical command is surfaced as missing, not guessed.

## 12. Service 9 — person-controller

Config:

```text
configs/research/track_b/person-controller.toml
```

Enable the service before build:

```yaml
enabled: true
```

Reset:

```bash
docker restart restgym_personcontroller
```

The restart resets the embedded Mongo test state.

## 13. Service 10 — pet-clinic

Config:

```text
configs/research/track_b/pet-clinic.toml
```

Three values are inseparable:

```text
RESTgym enabled: true
context path: /petclinic
Basic auth: admin:admin
```

`p2s prepare` enables the service, starts it, fetches the current OpenAPI document from the internal Spring service using Basic authentication, and stores it as:

```text
p2s_specs/petclinic.json
```

The v1.2 OCLI adapter then creates a profile equivalent to:

```bash
ocli profiles add p2s12_pet_clinic \
  --api-base-url http://localhost:9090/petclinic \
  --openapi-spec p2s_specs/petclinic.json \
  --api-basic-auth 'admin:admin' \
  --command-prefix ''
```

Reset:

```bash
docker restart restgym_petclinic
```

## 14. Service 11 — project-tracking-system

Config:

```text
configs/research/track_b/project-tracking-system.toml
```

Enable before build:

```yaml
enabled: true
```

Reset:

```bash
docker restart restgym_projecttrackingsystem
```

The restart recreates the H2 state through the service's Flyway migration/seed lifecycle.

## 15. Run all services sequentially

Do not run multiple RESTgym services simultaneously when they all bind host `9090` and `12345`.

A simple sequential loop is:

```bash
for svc in \
  blog erc20 features-service flight-search gestao-hospital \
  kafka-rest-proxy market notebook-manager person-controller \
  pet-clinic project-tracking-system
 do
  CFG="configs/research/track_b/${svc}.toml"
  RUN="runs/track-b/${svc}"
  echo "=== ${svc} ==="
  p2s doctor  --config "$CFG" --workdir "$RUN"
  p2s prepare --config "$CFG" --workdir "$RUN"
  p2s record  --config "$CFG" --workdir "$RUN"
  p2s compile --config "$CFG" --workdir "$RUN"
  p2s fuzz    --config "$CFG" --workdir "$RUN"
  p2s cleanup --config "$CFG" --workdir "$RUN"
 done
```

For Notebook Manager, set `P2S_NOTEBOOK_RESET_COMMAND` first. For Kafka, set `P2S_KAFKA_SPEC` if required by the retained checkout.

## 16. Track-B accounting

The framework can produce two kinds of candidate Golden:

- server fault (`5xx`);
- guarded `2xx` security-intent candidate.

The REST League FD construct is 5xx-only. Therefore Track-B paper-compatible accounting is:

1. run `p2s fd --golden-file ... --dedup-out ...`;
2. the command filters Golden records to HTTP 5xx before deduplication;
3. the dedup key uses endpoint, status, and extracted response/error signature;
4. report excluded 2xx candidates separately;
5. do not call the 2xx candidates verified vulnerabilities without an independent semantic verifier.

The retained strict status-aligned values are:

```text
blog       31
erc20      19
features   83
flight      0
gestao      1
kafka       7
market     29
notebook   25
person     58
pet        60
project     8
-----------
total     321
mean    29.18/API
```

A fresh stochastic run can differ. These values are audit targets for the retained artifacts.

## 17. Coverage and AUC boundary

Preserve JaCoCo `.exec`/CSV data for each service with the exact class scope used for that service. If a reset restarts the JVM, a final JaCoCo snapshot is not automatically cumulative across previous JVM lifetimes unless execution data are dumped/merged before restart.

The retained final-snapshot means are:

```text
branch  14.46%
line    27.37%
method  29.07%
```

No native P2S metric-time series was retained, so **do not derive a fake Roadrunner/AUC value from these final snapshots**.
