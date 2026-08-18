# P2S Framework v1.2 Research Configuration Reference

P2S v1.2 moves research-environment differences into TOML. The configuration is intentionally divided between **algorithmic target settings** and **lifecycle/environment settings**. Configured shell commands prefer Bash when available (including Git Bash on Windows) because the research procedures use Bash syntax.

## `[target]`

```toml
[target]
name = "seal_hackathon"
base_url = "http://localhost:8080/api"
openapi_spec = "seal_openapi.json"
state_adapter = "postgres"
executor_adapter = "ocli"
context_path_prefix = "/api"
golden_out = "golden_dataset.jsonl"
silver_out = "silver_dataset.jsonl"
checkpoint_file = "processed_flows.txt"
```

Fields:

- `name` — logical target identifier.
- `base_url` — API base used by raw HTTP or as an OCLI default.
- `openapi_spec` — source contract, resolved relative to `research.root_dir`.
- `state_adapter` — `postgres`, `docker`, `mongo`, `file`, `command`, or `stateless`.
- `executor_adapter` — usually `ocli`; `raw_http` is available for ablations.
- `context_path_prefix` — prefix removed before OpenAPI route matching, e.g. `/api` for SEAL.
- `golden_out`, `silver_out`, `checkpoint_file` — run artifacts written in `--workdir`.

## `[postgres]`

```toml
[postgres]
active_db = "seal_hackathon"
template_db = "seal_hackathon_snap"
admin_url = "postgresql://postgres:postgres@localhost:5432/postgres"
recreate_active_before_seed = true
seed_command = "..."
post_seed_commands = ["..."]
setup_script = ""
```

`recreate_active_before_seed=true` drops/recreates the active database before executing the configured seed command. `post_seed_commands` are useful for controlled test identities that must be normalized after schema/seed creation. `setup_script` remains as a backwards-compatible pre-snapshot hook.

## `[command_state]`

Use this for heterogeneous benchmark resets:

```toml
[command_state]
restore_snapshot_command = "docker restart service"
restore_snapshot_command_env = ""
create_snapshot_command = ""
create_snapshot_command_env = ""
working_directory = "."
restore_sleep_seconds = 2.0
```

If an `_env` field is set, P2S reads the actual command from that environment variable. This is how Notebook Manager explicitly exposes its missing/not-publicly-stable exact reset command rather than inventing one.

## Other state sections

```toml
[docker]
container_name = "target"
restart_sleep_seconds = 2.0

[mongo]
db_name = "db"
mongo_uri = "mongodb://localhost:27017"
dump_dir = "/tmp/p2s_mongo_snap"

[file_state]
active_path = "state.db"
backup_path = "state.db.p2s-snapshot"
```

## `[llm]`

```toml
[llm]
backend = "openai_compat"
base_url = "http://localhost:8081/v1"
model = "qwen35-9b-p2s"
api_key = "no-key"
api_key_env = ""
max_attempts = 6
```

For external providers prefer `api_key_env`:

```toml
api_key = ""
api_key_env = "DEEPSEEK_API_KEY"
```

## `[ocli]`

```toml
[ocli]
profile_name = "seal_p2s12_ft"
api_base_url = "http://localhost:8080/api"
openapi_spec = "seal_openapi.json"
bearer_token = ""
bearer_token_env = ""
bearer_token_file = ".p2s/token.txt"
basic_auth = ""
basic_auth_env = ""
basic_auth_file = ""
command_prefix = ""
throttle_delay_seconds = 0.015
timeout_seconds = 150
```

Credentials can come from literal config, environment, or a file produced by `[auth]`. Do not commit real third-party keys/tokens.

PetClinic uses `basic_auth = "admin:admin"`; SEAL uses a bearer token file.

## `[proxy]`

```toml
[proxy]
listen_port = 8090
target_host = "http://localhost:8080"
flow_strategy = "header"
reset_endpoint = "/auth/register"
output_file = "primitive_traces.jsonl"
mask_sensitive_headers = true
```

Flow strategies:

- `header` — flow ID comes from `X-Flow-ID`; used by SEAL.
- `endpoint` — registration/login reset semantics; used by AITasker source capture.

For retained Track B, RESTgym's own mitmproxy stays on host `9090`; the P2S proxy is not part of the primary run.

## `[openapi_setup]`

```toml
[openapi_setup]
source_url = "http://localhost:8080/api/v3/api-docs"
output_file = "seal_baseline_openapi.json"
server_url = "http://localhost:8080/api"
remove_paths = ["/auth/logout"]
remove_operations = ["DELETE /users/{id}", "DELETE /users/me"]
```

`p2s fetch-openapi` downloads JSON or YAML, normalizes the server URL, removes configured paths/operations, and writes the resulting contract.

## `[auth]`

```toml
[auth]
mode = "bearer_login"
login_url = "http://localhost:8080/api/auth/login"
login_body = { email = "coordinator@seal.eval", password = "Eval@1234567" }
token_json_field = "accessToken"
token_output_file = ".p2s/token.txt"
pre_login_commands = ["psql ... -c 'TRUNCATE revoked_tokens;'"]
```

`p2s auth` executes the preparation commands, performs the controlled login, extracts the configured JSON field, and stores the token with restrictive local-file intent. Treat the file as secret and exclude it from public release artifacts.

## `[[patches]]`

Four idempotent patch types are supported.

### Literal replace

```toml
[[patches]]
kind = "replace"
path = "apis/flight-search/auth.py"
find = '"userType": "USER"'
replace = '"userType": "ADMIN"'
required = true
count = 1
```

### Regex replace

```toml
[[patches]]
kind = "regex_replace"
path = "src/main/java/.../AppProperties.java"
find = '''private\s+int\s+accessTokenExpirationMinutes\s*=\s*\d+\s*;[^\n]*'''
replace = "private int accessTokenExpirationMinutes = 525600;"
count = 1
```

### Exact file write

```toml
[[patches]]
kind = "write"
path = "apis/features-service/restgym-api-config.yml"
content = "enabled: true\n"
```

### Append

```toml
[[patches]]
kind = "append"
path = "some.conf"
content = "setting=true\n"
```

`p2s patch` reports whether each patch changed the target or was already exact.

## `[research]`

```toml
[research]
root_dir = "$RESTGYM_ROOT"
prepare_commands = []
record_command = "python record_blog_full_52.py"
record_trace_source = "p2s_traces/blog/primitive_traces.jsonl"
record_snapshot_file = "baseline_primitive_traces.jsonl"
coverage_command = ""
cleanup_commands = []
readiness_url = ""
readiness_timeout_seconds = 60
readiness_interval_seconds = 1.0

time_budget_seconds = 3600
cyclic = true
clear_checkpoint_for_cyclic = true
reset_before_each_target = true
reset_before_each_flow = false
pre_step_replay = "none"
require_attack_flag_for_2xx = true
patch_openapi_required = true
runtime_openapi_file = "runtime_openapi.json"
```

Important fields:

- `root_dir` — root of the target repository. Environment variables are expanded.
- `prepare_commands` — target build/start commands after patches.
- `record_command` — target workload fixture.
- `record_trace_source` — optional primitive trace produced by the workload. If empty, `p2s record` freezes `proxy.output_file`. If set, it freezes this root-relative file instead.
- `record_snapshot_file` — immutable baseline trace inside `--workdir`.
- `time_budget_seconds` — hard wall-clock budget.
- `cyclic` — repeat flow corpus until budget expires.
- `reset_before_each_target` — reset state before every target step (Track B).
- `reset_before_each_flow` — rebuild seed baseline before first target of a flow (Track A/source generation).
- `pre_step_replay` — `last`, `all`, or `none`.
- `require_attack_flag_for_2xx` — stricter Track-B candidate guard.
- `patch_openapi_required` — create a runtime contract with non-path required constraints relaxed for omission tests; source spec is left intact.

## Framework-native config inventory

```text
configs/research/
├── aitasker_training.toml
├── track_a_baselines.toml
├── track_a_seal_p2s.toml
├── track_a_seal_base_qwen.toml
├── track_a_seal_deepseek.toml
└── track_b/
    ├── blog.toml
    ├── erc20.toml
    ├── features-service.toml
    ├── flight-search.toml
    ├── gestao-hospital.toml
    ├── kafka-rest-proxy.toml
    ├── market.toml
    ├── notebook-manager.toml
    ├── person-controller.toml
    ├── pet-clinic.toml
    └── project-tracking-system.toml
```
