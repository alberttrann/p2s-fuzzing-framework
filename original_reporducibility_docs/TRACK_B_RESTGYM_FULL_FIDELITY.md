# P2S Track B — Full-Fidelity RESTgym 11-Service Reproduction

This reviewer-facing document preserves the service-specific RESTgym environment contract needed for the Track-B experiments. Configuration patches, authentication/proxy behavior, context paths, launch parameters, and reset adapters are treated as **normative experimental configuration**, not optional troubleshooting notes.

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
