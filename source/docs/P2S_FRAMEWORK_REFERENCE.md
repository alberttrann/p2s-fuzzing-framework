# P2S Framework — Unified Technical Reference

> **Execution-Verified API Security Testing & Dataset Generation Framework**
>
> P2S (**Proxy → Primitive → Self-play**) captures real HTTP traffic through a transparent proxy, compiles it into typed CLI traces via OCLI, and orchestrates an LLM-powered self-play mutation loop that verifies every mutation against a live backend before persisting it. The result is a **ground-truth-verified** dataset of exploitable API faults (Goldens) and defensive boundaries (Silvers), suitable for direct security reporting or SFT fine-tuning.
>
> The separate **Colab A100 SFT training notebook** is distributed as `p2s_colab_train.py` and is not part of this document.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Installation & Packaging](#2-installation--packaging)
3. [Configuration System](#3-configuration-system)
4. [Adapters Layer](#4-adapters-layer)
   - 4.1 State Adapters
   - 4.2 Execution Adapters
   - 4.3 LLM Adapters
5. [Proxy Capture](#5-proxy-capture)
6. [Trace Compiler](#6-trace-compiler)
7. [Taxonomy & Prompt Builder](#7-taxonomy--prompt-builder)
8. [Core Fuzzer — Eval Mode](#8-core-fuzzer--eval-mode)
9. [Data Generator — Train Mode](#9-data-generator--train-mode)
10. [Dataset Builder](#10-dataset-builder)
11. [Analytics Suite](#11-analytics-suite)
    - 11.1 Comparative Analyzer
    - 11.2 Offline Tier-2 Reclassifier
    - 11.3 Cumulative M1 Analyzer
    - 11.4 False-Positive Verifier & Deduplicator
12. [Unified CLI Runner](#12-unified-cli-runner)
13. [Example Configurations & Hooks](#13-example-configurations--hooks)
14. [Workflow Guides](#14-workflow-guides)

---

## 1. Architecture Overview

### Directory Tree

```text
p2s_framework/
├── p2s/
│   ├── config.py                        # TOML loader → typed dataclasses
│   ├── proxy/
│   │   ├── __init__.py
│   │   └── core_proxy.py                # Transparent traffic interceptor
│   ├── compiler/
│   │   ├── __init__.py
│   │   └── compiler.py                  # Raw trace → OCLI command compiler
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── taxonomy.py                  # 15-vector taxonomy & prompt builder
│   │   ├── fuzzer.py                    # Eval: execution-verified self-play loop
│   │   ├── generator.py                 # Train: Teacher-Critic nudge loop
│   │   └── adapters/
│   │       ├── __init__.py
│   │       ├── state_adapter.py         # Postgres | Mongo | File | Docker | Stateless
│   │       ├── executor.py              # OCLI | Raw HTTP
│   │       └── llm_adapter.py           # OpenAI-compat | Transformers
│   ├── dataset/
│   │   ├── __init__.py
│   │   └── builder.py                   # Stratified corpus builder
│   └── analytics/
│       ├── __init__.py
│       ├── analyzer.py                  # Cross-backend M1/M2/M3 comparison
│       ├── reclassifier.py              # Offline Tier-2 SLM vector classifier
│       ├── m1_analyzer.py               # Cumulative log-based M1 parser
│       └── verifier.py                  # False-positive filter & fault deduplicator
├── p2s_runner.py                        # Master CLI entry point (9 modes)
├── pyproject.toml
├── configs/
│   ├── seal_hackathon.toml
│   └── aitasker.toml
└── hooks/
    └── seal_setup_hook.py               # Example pre-snapshot hook
```

### Pipeline Flow

```
[Target Backend]
      │  (HTTP Traffic)
      ▼
┌─────────────────────────────────────────────────┐
│  p2s proxy       → primitive_traces.jsonl        │  Raw HTTP logs
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│  p2s compile     → compiled_traces.jsonl         │  OCLI commands + catalog
│                  → ocli_catalog.json             │
└────────────────────┬────────────────────────────┘
                     │
          ┌──────────┴──────────┐
          ▼                     ▼
   p2s fuzz                p2s generate-data
   (Eval Mode)             (Train Mode)
   fuzzer.py               generator.py
   │                       │
   └──────────┬────────────┘
              ▼
   golden_dataset.jsonl   ← 500 crashes + RBAC bypasses
   silver_dataset.jsonl   ← Defensive boundaries (4xx)
              │
              ▼
   p2s prepare-dataset → final_training_dataset.jsonl
              │
              ▼
   p2s verify            ← False-positive audit
   p2s analyze           ← Cross-backend M1/M2/M3 report
   p2s reclassify        ← Offline Tier-2 vector re-labelling
   p2s m1                ← Cumulative syntax pass rate
```

### Three Evaluation Metrics

| Metric | Definition |
|--------|-----------|
| **M1 — Syntax Pass Rate** | `API responses / (API responses + CLI syntax failures)` |
| **M2 — Boundary Prediction** | Exact-match and class-match accuracy of `# ASSERT: status == XXX` |
| **M3 — Kill Rate** | `Golden records / Total records` |

---

## 2. Installation & Packaging

### `pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "p2s-framework"
version = "1.0.0"
description = "P2S: Execution-Verified API Security Testing & Dataset Generation Framework"
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
    "httpx>=0.23",
    "psycopg2-binary>=2.9",
    "openai>=1.0",
    "tomli>=2.0; python_version < '3.11'"
]

[project.scripts]
p2s = "p2s_runner:main"

[tool.setuptools.packages.find]
include = ["p2s", "p2s.*"]
```

### Install

```bash
pip install -e .
# Verify
p2s --help
```

---

## 3. Configuration System

### `p2s/config.py`

Parses TOML files into strictly typed Python dataclasses. All runtime adapter selection is driven by the values in the TOML — no code changes needed when switching targets.

```python
"""
P2S Configuration Parser: Loads TOML configurations into strictly typed dataclasses.
"""
import os
import sys
from dataclasses import dataclass, field

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # Fallback for Python < 3.11

@dataclass
class TargetConfig:
    name: str
    base_url: str
    openapi_spec: str
    state_adapter: str = "stateless"
    executor_adapter: str = "ocli"
    golden_out: str = "golden_dataset.jsonl"
    silver_out: str = "silver_dataset.jsonl"
    checkpoint_file: str = "processed_flows.txt"

@dataclass
class PostgresConfig:
    active_db: str = ""
    template_db: str = ""
    admin_url: str = ""
    seed_command: str = ""
    setup_script: str = ""   # Path to pre-snapshot Python hook

@dataclass
class LLMConfig:
    backend: str = "openai_compat"
    base_url: str = "http://localhost:8081/v1"
    model: str = "qwen35-9b"
    api_key: str = "no-key"
    max_attempts: int = 6

@dataclass
class ProxyConfig:
    listen_port: int = 8090
    target_host: str = "http://localhost:8080"
    flow_strategy: str = "header"
    reset_endpoint: str = "/auth/register"
    output_file: str = "primitive_traces.jsonl"

@dataclass
class P2SConfig:
    target: TargetConfig
    llm: LLMConfig
    proxy: ProxyConfig
    postgres: PostgresConfig = field(default_factory=PostgresConfig)

def load_config(file_path: str) -> P2SConfig:
    if not os.path.exists(file_path):
        print(f"[FATAL] Configuration file not found: {file_path}")
        sys.exit(1)
    
    with open(file_path, "rb") as f:
        data = tomllib.load(f)

    target = TargetConfig(**data.get("target", {}))
    llm = LLMConfig(**data.get("llm", {}))
    proxy = ProxyConfig(**data.get("proxy", {}))
    postgres = PostgresConfig(**data.get("postgres", {}))

    return P2SConfig(target=target, llm=llm, proxy=proxy, postgres=postgres)
```

---

## 4. Adapters Layer

### 4.1 State Adapters — `p2s/engine/adapters/state_adapter.py`

Handles environment snapshotting and restoration. Each adapter implements a `create_snapshot()` / `restore_snapshot()` contract. The active adapter is selected at runtime from the TOML `state_adapter` key.

```python
"""
P2S State Adapters: Handles target environment snapshotting and restoration.
Supports PostgreSQL (with optional initial SQL seeding & post-seed alignment),
MongoDB, File DBs, Docker, and Stateless modes.
"""
from abc import ABC, abstractmethod
import subprocess
import time
import shutil
import os

class BaseStateAdapter(ABC):
    @abstractmethod
    def create_snapshot(self) -> None: pass
    @abstractmethod
    def restore_snapshot(self) -> None: pass


class PostgresTemplateAdapter(BaseStateAdapter):
    """Sub-second state reset for PostgreSQL using CREATE DATABASE WITH TEMPLATE."""

    def __init__(self, active_db: str, template_db: str, admin_uri: str,
                 seed_command: str = None, pre_snapshot_hook: callable = None):
        import psycopg2
        from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
        self.active_db = active_db
        self.template_db = template_db
        self.admin_uri = admin_uri
        self.seed_command = seed_command
        self.pre_snapshot_hook = pre_snapshot_hook
        self.psycopg2 = psycopg2
        self.iso_level = ISOLATION_LEVEL_AUTOCOMMIT

    def _execute_sql(self, query: str, db_name: str = None):
        uri = self.admin_uri if not db_name else f"{self.admin_uri.rsplit('/', 1)[0]}/{db_name}"
        conn = self.psycopg2.connect(uri)
        conn.set_isolation_level(self.iso_level)
        with conn.cursor() as cur:
            try: cur.execute(query)
            except Exception: pass
        conn.close()

    def _terminate_connections(self, db_name: str):
        self._execute_sql(
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname='{db_name}' AND pid<>pg_backend_pid();"
        )

    def create_snapshot(self):
        # Auto-seed if template_db does not exist yet
        if not self._db_exists(self.template_db):
            if self.seed_command:
                print(f"[*] Seeding active database '{self.active_db}' before first snapshot...")
                subprocess.run(self.seed_command, shell=True, check=True)
            if self.pre_snapshot_hook:
                print(f"[*] Executing pre-snapshot hook...")
                self.pre_snapshot_hook(self.active_db)

        self._execute_sql(f"ALTER DATABASE {self.active_db} ALLOW_CONNECTIONS = false;")
        self._terminate_connections(self.active_db)
        self._execute_sql(f"DROP DATABASE IF EXISTS {self.template_db};")

        snapped = False
        for _ in range(5):
            try:
                self._execute_sql(
                    f"CREATE DATABASE {self.template_db} WITH TEMPLATE {self.active_db};"
                )
                snapped = True
                break
            except Exception:
                time.sleep(0.2)
                self._terminate_connections(self.active_db)

        self._execute_sql(f"ALTER DATABASE {self.active_db} ALLOW_CONNECTIONS = true;")
        if not snapped:
            raise RuntimeError("Database snapshot creation failed after 5 attempts.")

    def restore_snapshot(self):
        try:
            self._execute_sql(f"ALTER DATABASE {self.active_db} ALLOW_CONNECTIONS = false;")
            self._terminate_connections(self.active_db)

            restored = False
            for _ in range(5):
                try:
                    self._execute_sql(f"DROP DATABASE IF EXISTS {self.active_db};")
                    self._execute_sql(
                        f"CREATE DATABASE {self.active_db} WITH TEMPLATE {self.template_db};"
                    )
                    restored = True
                    break
                except Exception:
                    time.sleep(0.2)
                    self._terminate_connections(self.active_db)

            if not restored:
                raise RuntimeError("Database restore failed after 5 attempts.")
        finally:
            self._execute_sql(f"ALTER DATABASE {self.active_db} ALLOW_CONNECTIONS = true;")
            time.sleep(1.0)

    def _db_exists(self, db_name: str) -> bool:
        conn = self.psycopg2.connect(self.admin_uri)
        conn.set_isolation_level(self.iso_level)
        with conn.cursor() as cur:
            cur.execute(f"SELECT 1 FROM pg_database WHERE datname='{db_name}';")
            exists = cur.fetchone() is not None
        conn.close()
        return exists


class MongoDumpAdapter(BaseStateAdapter):
    def __init__(self, db_name: str, mongo_uri: str, dump_dir: str = "/tmp/p2s_mongo_snap"):
        self.db_name = db_name
        self.mongo_uri = mongo_uri
        self.dump_dir = dump_dir

    def create_snapshot(self):
        if os.path.exists(self.dump_dir): shutil.rmtree(self.dump_dir)
        subprocess.run(
            ["mongodump", "--uri", self.mongo_uri, "-d", self.db_name, "-o", self.dump_dir],
            check=True, stdout=subprocess.DEVNULL
        )

    def restore_snapshot(self):
        dump_path = os.path.join(self.dump_dir, self.db_name)
        subprocess.run(
            ["mongorestore", "--uri", self.mongo_uri, "--drop", "-d", self.db_name, dump_path],
            check=True, stdout=subprocess.DEVNULL
        )


class FileBackupAdapter(BaseStateAdapter):
    def __init__(self, active_file_path: str, backup_file_path: str):
        self.active = active_file_path
        self.backup = backup_file_path

    def create_snapshot(self): shutil.copy2(self.active, self.backup)
    def restore_snapshot(self): shutil.copy2(self.backup, self.active)


class DockerRestartAdapter(BaseStateAdapter):
    def __init__(self, container_name: str, sleep_time: float = 2.0):
        self.container_name = container_name
        self.sleep_time = sleep_time

    def create_snapshot(self): pass

    def restore_snapshot(self):
        subprocess.run(
            ["docker", "restart", self.container_name],
            check=True, stdout=subprocess.DEVNULL
        )
        time.sleep(self.sleep_time)


class StatelessAdapter(BaseStateAdapter):
    def create_snapshot(self): pass
    def restore_snapshot(self): pass
```

**Adapter selection matrix:**

| `state_adapter` value | Class | Use case |
|---|---|---|
| `postgres` | `PostgresTemplateAdapter` | Spring Boot / NestJS / Django with Postgres |
| `mongo` | `MongoDumpAdapter` | Genome-Nexus, any MongoDB backend |
| `file` | `FileBackupAdapter` | SQLite or embedded H2 |
| `docker` | `DockerRestartAdapter` | Containerised stateful services |
| `stateless` | `StatelessAdapter` | REST APIs with no persistent state |

---

### 4.2 Execution Adapters — `p2s/engine/adapters/executor.py`

Dispatches mutated payloads to the target. `OcliExecutorAdapter` is the default P2S path; `RawHttpExecutorAdapter` is the Swagger-ICL ablation baseline.

```python
"""
P2S Executor Adapters: Dispatches mutated commands to the target.
Supports OCLI (OpenAPI-to-CLI) execution and Raw HTTP JSON dispatch.
Includes bash expression expansion, arg capping, and auto-profile setup.
"""
from abc import ABC, abstractmethod
import subprocess
import shlex
import os
import sys
import re
import time
import json

class BaseExecutorAdapter(ABC):
    @abstractmethod
    def execute(self, payload: str | dict, bearer_token: str = None) -> tuple[int, str, str]:
        pass

    @abstractmethod
    def get_help(self, command_name: str, openapi_path: str = None, method: str = None) -> str:
        pass


class OcliExecutorAdapter(BaseExecutorAdapter):
    def __init__(self, profile_name: str = "seal",
                 target_url: str = "http://localhost:8080/api",
                 throttle_delay: float = 0.015,
                 timeout: int = 150,
                 catalog_path: str = "ocli_catalog.json"):
        self.profile_name = profile_name
        self.target_url = target_url
        self.throttle_delay = throttle_delay
        self.timeout = timeout

        # Load object query parameter names for formatting
        self.object_query_params = set()
        if os.path.exists(catalog_path):
            try:
                with open(catalog_path, "r", encoding="utf-8") as f:
                    for entry in json.load(f).values():
                        for pn, pi in entry.get("flags", {}).items():
                            if pi.get("in") == "query" and pi.get("type") == "object":
                                self.object_query_params.add(pn)
            except Exception: pass

        if not self.object_query_params:
            self.object_query_params = {"p", "pageable"}

        # Git Bash discovery for Windows
        self.shell_exec = None
        if sys.platform == "win32":
            import shutil
            self.shell_exec = shutil.which("bash")
            if not self.shell_exec:
                for p in [
                    r"C:\Program Files\Git\bin\bash.exe",
                    r"C:\Program Files\Git\usr\bin\bash.exe",
                    os.path.expanduser(r"~\AppData\Local\Programs\Git\bin\bash.exe")
                ]:
                    if os.path.exists(p): self.shell_exec = p; break

        self._ensure_profile_exists()

    def _ensure_profile_exists(self):
        """Auto-registers OCLI profile if missing."""
        ini = os.path.join(os.path.expanduser("~"), ".ocli", "profiles.ini")
        found = []
        if os.path.exists(ini):
            with open(ini, "r", encoding="utf-8") as f:
                found = re.findall(r'\[(.*?)\]', f.read())
        if self.profile_name not in found:
            print(f"[*] Auto-registering OCLI profile '{self.profile_name}'...")
            cmd = (
                f'ocli profiles add {self.profile_name} '
                f'--api-base-url {self.target_url} '
                f'--openapi-spec {self.target_url}/v3/api-docs '
                f'--api-bearer-token "" --command-prefix ""'
            )
            subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL)
            subprocess.run(f"ocli use {self.profile_name}", shell=True, stdout=subprocess.DEVNULL)

    def get_help(self, command_name: str, openapi_path: str = None, method: str = None) -> str:
        res = subprocess.run(f"{command_name} --help", shell=True, capture_output=True, text=True)
        help_text = res.stdout.strip() if res.stdout.strip() else res.stderr.strip()
        help_text = re.sub(r'--profile\s+string.*?\n', '', help_text, flags=re.IGNORECASE)
        help_text = re.sub(r'-p,\s+--profile\s+string.*?\n', '', help_text, flags=re.IGNORECASE)
        return help_text

    def _expand_shell_expressions(self, s: str) -> str:
        """Expands Python/shell expression hallucinations from LLM outputs."""
        _PRINT_REPEAT = re.compile(
            r'(?:\$\(|`)\s*python3?\s+-c\s+(?:["\']print\s*\(\s*["\'](.)["\']\s*\*\s*(\d+)\s*\)["\'])'
            r'\s*(?:\)|`)'
        )
        def _er(m):
            try: r = m.group(1) * min(int(m.group(2)), 100000)
            except: r = 'A' * 1000
            return '"' + r.replace('\\', '\\\\').replace('"', '\\"') + '"'
        s = _PRINT_REPEAT.sub(_er, s)

        _URANDOM = re.compile(
            r'\$\(\s*python3?\s+-c\s+["\']import\s+os;\s*print\s*\('
            r'\s*os\.urandom\s*\(\s*(\d+)\s*\)\.hex\s*\(\s*\)\s*\)["\']\s*\)'
        )
        def _eu(m):
            try: import os as _o; return '"' + _o.urandom(min(int(m.group(1)), 1024)).hex() + '"'
            except: return '"deadbeef"'
        s = _URANDOM.sub(_eu, s)

        s = re.sub(r'["\'](.)["\']\.repeat\s*\(\s*(\d+)\s*\)', _er, s)
        s = re.sub(r'(?<![(\w])["\'](.)["\']\s*\*\s*(\d+)(?![\w(])', _er, s)
        return s

    def _esc_singles(self, s: str) -> str:
        def _f(m): return '"' + re.sub(r"(?<!\\)'", r"\\'", m.group(1)) + '"'
        return re.sub(r'"((?:[^"\\]|\\.)*)"', _f, s)

    def _retok(self, s: str) -> str:
        _FB = re.compile(r'--([a-zA-Z][\w-]*)\s*')
        ms = list(_FB.finditer(s))
        if not ms: return re.sub(r'[\s"\'\]}]+$', '', s)
        parts = [s[:ms[0].start()].strip()]
        for i, m in enumerate(ms):
            fl = m.group(1); se = m.end(); ee = ms[i+1].start() if i+1 < len(ms) else len(s)
            seg = s[se:ee].strip()
            if not seg:
                parts.append(f"--{fl}")
                continue
            rv = seg
            for q in ("'", '"'):
                f_idx = seg.find(q); l_idx = seg.rfind(q)
                if f_idx != -1 and l_idx != -1 and l_idx > f_idx:
                    rv = seg[f_idx+1:l_idx]; break
            else: rv = seg.strip()
            if fl == "body": rv = rv.replace('\\"', '"')
            parts.append(
                f"--{fl} '{rv.replace(chr(39), chr(39)+chr(34)+chr(39)+chr(34)+chr(39))}'"
            )
        return " ".join(parts)

    def execute(self, cmd_str: str, bearer_token: str = None) -> tuple[int, str, str]:
        time.sleep(self.throttle_delay)
        if not cmd_str or str(cmd_str).strip().lower() in ["none", "null", ""]:
            return 1, "", "Error: empty command"

        cmd_str = str(cmd_str).strip()
        cmd_str = re.sub(r'^.*?"mutated_command"\s*:\s*"', '', cmd_str)
        cmd_str = re.sub(r'^[{"\s]+(?=ocli\s)', '', cmd_str)

        body_match = re.search(r"--body\s+'(.*?)'", cmd_str)
        if body_match:
            raw_body = body_match.group(1)
            cmd_str = cmd_str.replace(raw_body, raw_body.replace('\\"', '"'))

        cmd_str = self._expand_shell_expressions(cmd_str)
        cmd_str = self._esc_singles(cmd_str)
        cmd_str = self._retok(cmd_str)

        for pn in self.object_query_params:
            fp = rf"--{re.escape(pn)}\s+"
            if re.search(fp, cmd_str) and not (
                re.search(fp + r"'\s*\{", cmd_str) or re.search(fp + r'"\s*\{', cmd_str)
            ):
                cmd_str = re.sub(
                    fp + r"(?:'[^']*'|\"[^\"]*\"|[^\s'\"-][^\s]*)",
                    f"--{pn} '{{\"page\":0,\"size\":20}}'",
                    cmd_str
                )

        env = os.environ.copy()
        MAX_FLAG_VALUE_LEN = 8192
        _lvc = [0]

        def _cap(cmd):
            def _cc(m):
                if len(m.group(2)) <= MAX_FLAG_VALUE_LEN: return m.group(0)
                ek = f"P2S_LONG_VAL_{_lvc[0]}"
                env[ek] = m.group(2)[:4096]; _lvc[0] += 1
                return f'--{m.group(1)} "${ek}"'
            cmd = re.sub(r"--(\w+)\s+'([^']{" + str(MAX_FLAG_VALUE_LEN) + r",})'", _cc, cmd)
            cmd = re.sub(r'--(\w+)\s+"([^"]{' + str(MAX_FLAG_VALUE_LEN) + r',})"', _cc, cmd)
            return cmd

        cmd_str = _cap(cmd_str)
        cmd_str = re.sub(r'\s+--profile\s+(?:"[^"]*"|\'[^\']*\'|[^\s]+)', '', cmd_str)
        cmd_str = re.sub(r'\s+-p\s+(?:"[^"]*"|\'[^\']*\'|[^\s]+)', '', cmd_str)
        cmd_str = cmd_str.strip()

        if bearer_token and "--api-bearer-token" not in cmd_str:
            cmd_str += f" --api-bearer-token {shlex.quote(bearer_token)}"
        if "--profile" not in cmd_str and "ocli " in cmd_str:
            cmd_str += f" --profile {self.profile_name}"

        cmd_str = cmd_str.replace('\x00', '\\x00')

        if sys.platform == "win32" and self.shell_exec:
            import tempfile
            fd, ts = tempfile.mkstemp(suffix=".sh", text=True)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f: f.write(cmd_str)
                r = subprocess.run(
                    [self.shell_exec, ts.replace("\\", "/")],
                    capture_output=True, text=True, env=env, timeout=self.timeout
                )
                return r.returncode, r.stdout, r.stderr
            except subprocess.TimeoutExpired: return 504, "", "Request timed out"
            finally:
                try: os.remove(ts)
                except: pass

        try:
            r = subprocess.run(
                cmd_str, shell=True, capture_output=True, text=True, env=env, timeout=self.timeout
            )
            return r.returncode, r.stdout, r.stderr
        except subprocess.TimeoutExpired:
            return 504, "", "Request timed out"


class RawHttpExecutorAdapter(BaseExecutorAdapter):
    """Bypasses OCLI to send raw HTTP JSON payloads directly (Swagger-ICL Ablation)."""

    def __init__(self, base_url: str, spec_path: str):
        import httpx
        self.httpx = httpx
        self.base_url = base_url.rstrip("/")
        with open(spec_path, "r", encoding="utf-8") as f:
            self.spec = json.load(f)

    def _resolve_refs(self, node):
        """Recursively inlines $ref pointers."""
        if isinstance(node, dict):
            if "$ref" in node:
                ref_path = node["$ref"].replace("#/components/schemas/", "")
                resolved = self.spec.get("components", {}).get("schemas", {}).get(ref_path, {})
                return self._resolve_refs(resolved)
            return {k: self._resolve_refs(v) for k, v in node.items()}
        elif isinstance(node, list):
            return [self._resolve_refs(i) for i in node]
        return node

    def get_help(self, command_name: str, openapi_path: str = None, method: str = None) -> str:
        if not openapi_path or not method: return "(Schema unavailable)"
        route_spec = self.spec.get("paths", {}).get(openapi_path, {}).get(method.lower(), {})
        return json.dumps(self._resolve_refs(route_spec), indent=2)

    def execute(self, req_dict: dict | str, bearer_token: str = None) -> tuple[int, str, str]:
        if not isinstance(req_dict, dict):
            try: req_dict = json.loads(req_dict)
            except Exception: return 1, "", "M1_SYNTAX_FAIL: Payload is not a valid JSON dict"

        method = str(req_dict.get("method", "GET")).upper()
        path = str(req_dict.get("path", "/")).strip()
        query = req_dict.get("query", {})
        headers = req_dict.get("headers", {})
        body = req_dict.get("body", None)

        if not isinstance(headers, dict): headers = {}
        if not path.startswith("/"): path = "/" + path
        if bearer_token and "Authorization" not in headers and "authorization" not in headers:
            headers["Authorization"] = f"Bearer {bearer_token}"

        try:
            with self.httpx.Client(timeout=15.0) as client:
                resp = client.request(
                    method=method, url=f"{self.base_url}{path}", params=query,
                    headers=headers,
                    json=body if isinstance(body, (dict, list)) else None,
                    content=str(body) if isinstance(body, str) else None
                )
                return 0, f"status code {resp.status_code}\n{resp.text}", ""
        except self.httpx.TimeoutException:
            return 504, "", "status code 504 Request timed out"
        except Exception as exc:
            return 1, "", f"HTTP_DISPATCH_ERROR: {exc}"
```

---

### 4.3 LLM Adapters — `p2s/engine/adapters/llm_adapter.py`

Provides a uniform `query(messages, temperature) → dict` interface across OpenAI-compatible servers (LM Studio, llama.cpp, DeepSeek) and local HuggingFace Transformers models. Includes the three-tier M2 `predicted_status` extractor.

```python
"""
P2S LLM Adapters: Standardized interface for querying language models.
Supports OpenAI-compatible APIs and local HuggingFace Transformers (Safetensors).
Includes 3-Tier M2 (predicted_status) extraction.
"""
from abc import ABC, abstractmethod
import json
import re

class BaseLLMAdapter(ABC):
    @abstractmethod
    def query(self, messages: list, temperature: float) -> dict:
        pass

    def _parse_output(self, raw_text: str) -> dict:
        """Robust multi-pass extractor for P2S formatting & 3-tier M2 status extraction."""
        raw_text = raw_text.strip()
        parsed = {}

        # 1. Code-Fence Extraction (P2S Native Format)
        bash_match = re.search(
            r'```[a-zA-Z]*\s*\n?(ocli[\s\S]*?)\n?\s*```', raw_text, re.IGNORECASE
        )
        if bash_match:
            cmd = bash_match.group(1).strip()
            cmd = re.sub(r'\n#\s*ASSERT:.*$', '', cmd, flags=re.MULTILINE).strip()
            cmd = re.sub(r'#\s*ASSERT:.*', '', cmd).strip()
            fence_start = raw_text.find('```')
            reasoning = re.sub(r'</?think>', '', raw_text[:fence_start]).strip() \
                        if fence_start > 0 else ""
            if cmd:
                parsed = {"reasoning": reasoning, "mutated_command": cmd}

        # 2. JSON Extraction (DeepSeek / Base Model Fallback)
        if not parsed:
            json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if json_match:
                try:
                    parsed = json.loads(json_match.group(0), strict=False)
                except json.JSONDecodeError:
                    pass

        # 3. Think-tag + bare command fallback
        if not parsed:
            reasoning = ""
            tm = re.search(r'<think>(.*?)</think>', raw_text, re.DOTALL | re.IGNORECASE)
            if tm: reasoning = tm.group(1).strip()
            cmd_match = re.search(r'^(ocli\s+.+)$', raw_text, re.MULTILINE | re.IGNORECASE)
            cmd = cmd_match.group(1).strip() if cmd_match else ""
            cmd = re.sub(r'#\s*ASSERT:.*', '', cmd).strip()
            if cmd or reasoning:
                parsed = {"reasoning": reasoning, "mutated_command": cmd}

        # M2 Three-Tier Prediction Extraction
        predicted_status = None
        # Tier 1: JSON key
        _ps = parsed.get("predicted_status")
        if _ps is not None:
            try: predicted_status = int(_ps)
            except (ValueError, TypeError): pass

        # Tier 2: Raw Response ASSERT comment
        if predicted_status is None:
            assert_match = re.search(r'#\s*ASSERT:\s*status\s*==\s*(\d{3})', raw_text)
            if assert_match:
                predicted_status = int(assert_match.group(1))

        # Tier 3: Reasoning / Command Fallback
        if predicted_status is None:
            combined_text = (parsed.get("reasoning", "") or "") + " " + \
                            (parsed.get("mutated_command", "") or "")
            assert_match = re.search(r'#\s*ASSERT:\s*status\s*==\s*(\d{3})', combined_text)
            if assert_match:
                predicted_status = int(assert_match.group(1))

        parsed["predicted_status"] = predicted_status
        parsed["_raw_response"] = raw_text
        return parsed


class OpenAICompatAdapter(BaseLLMAdapter):
    """Works with OpenAI, DeepSeek, LM Studio, and llama.cpp."""

    def __init__(self, base_url: str, api_key: str, model_name: str):
        from openai import OpenAI
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model_name = model_name

    def query(self, messages: list, temperature: float) -> dict:
        resp = self.client.chat.completions.create(
            model=self.model_name, messages=messages,
            temperature=temperature, max_tokens=8192
        )
        content = resp.choices[0].message.content or ""
        reasoning_content = getattr(resp.choices[0].message, "reasoning_content", "")
        combined = (reasoning_content + "\n" + content).strip() if reasoning_content else content
        return self._parse_output(combined)


class TransformersAdapter(BaseLLMAdapter):
    """Runs local Safetensor/PyTorch models directly on GPU."""

    def __init__(self, model_path: str):
        self._apply_runtime_patches()
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[*] Loading Local Transformers Model: {model_path} on {self.device}...")
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_path, device_map="auto", torch_dtype=torch.bfloat16, trust_remote_code=False
        )
        self.model.eval()

    def _apply_runtime_patches(self):
        """Fixes PyTorch weight-init and Safetensors double-prefix key mapper bugs."""
        try:
            import torch, torch.nn.init as init, safetensors.torch, safetensors

            if hasattr(init, "_no_grad_normal_"):
                orig = init._no_grad_normal_
                def patched(tensor, mean=0., std=1., generator=None):
                    return tensor if tensor.dtype in (torch.uint8, torch.int8) \
                           else orig(tensor, mean, std, generator)
                init._no_grad_normal_ = patched

            orig_load_file = safetensors.torch.load_file
            def patched_load_file(filename, device="cpu"):
                sd = orig_load_file(filename, device=device)
                PREFIX = "model.language_model.language_model."
                return {
                    ("model." + k[len(PREFIX):] if k.startswith(PREFIX) else k): v
                    for k, v in sd.items()
                }
            safetensors.torch.load_file = patched_load_file

            orig_safe_open = safetensors.safe_open
            class PatchedSafeOpen:
                def __init__(self, *a, **kw):
                    self.handle = orig_safe_open(*a, **kw)
                    PREFIX = "model.language_model.language_model."
                    self._keys_list, self._fwd = [], {}
                    for k in self.handle.keys():
                        mk = ("model." + k[len(PREFIX):]) if k.startswith(PREFIX) else k
                        self._keys_list.append(mk); self._fwd[mk] = k
                def keys(self): return self._keys_list
                def get_tensor(self, k): return self.handle.get_tensor(self._fwd.get(k, k))
                def get_slice(self, k): return self.handle.get_slice(self._fwd.get(k, k))
                def __enter__(self): return self
                def __exit__(self, *a): pass
            safetensors.safe_open = PatchedSafeOpen
        except ImportError:
            pass

    def query(self, messages: list, temperature: float) -> dict:
        import torch
        text = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self.tokenizer(text, return_tensors="pt").to(self.device)
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs, max_new_tokens=8192, temperature=temperature,
                do_sample=(temperature > 0),
                pad_token_id=self.tokenizer.eos_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
                repetition_penalty=1.1
            )
        raw = self.tokenizer.decode(
            outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True
        )
        return self._parse_output(raw)
```

---

## 5. Proxy Capture — `p2s/proxy/core_proxy.py`

A `ThreadingHTTPServer` that transparently forwards all traffic to the target, logs every request/response as a structured JSONL trace step, and splits them into named flows using a pluggable `FlowStrategy`.

```python
"""
P2S Transparent Proxy: Captures HTTP traffic into primitive traces.
Supports pluggable Flow Separation Strategies.
"""
import json
import uuid
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import httpx

class FlowStrategy:
    def determine_flow_and_step(self, method: str, path: str, headers: dict) -> tuple[str, int]:
        pass

class HeaderFlowStrategy(FlowStrategy):
    """Flows are dictated by a custom X-Flow-ID header injected by test scripts (SEAL mode)."""
    def __init__(self):
        self.lock = threading.Lock()
        self.flow_steps = {}

    def determine_flow_and_step(self, method: str, path: str, headers: dict):
        raw_flow_id = headers.get("X-Flow-ID", f"flow_{uuid.uuid4().hex[:12]}").strip()
        if not raw_flow_id: raw_flow_id = f"flow_{uuid.uuid4().hex[:12]}"
        path_only = path.split("?")[0]
        is_reset = (method == "POST" and path_only.endswith("/auth/register"))
        with self.lock:
            if is_reset or raw_flow_id not in self.flow_steps:
                self.flow_steps[raw_flow_id] = 1
            else:
                self.flow_steps[raw_flow_id] += 1
            return raw_flow_id, self.flow_steps[raw_flow_id]

class EndpointResetStrategy(FlowStrategy):
    """A global flow resets whenever a configured endpoint is hit (AITasker mode)."""
    def __init__(self, reset_endpoint: str):
        self.reset_endpoint = reset_endpoint
        self.lock = threading.Lock()
        self.current_flow_id = f"flow_{uuid.uuid4().hex[:12]}"
        self.step_counter = 0

    def determine_flow_and_step(self, method: str, path: str, headers: dict):
        with self.lock:
            path_only = path.split("?")[0]
            is_reset = (method.upper() == "POST" and path_only.endswith(self.reset_endpoint))
            if is_reset:
                self.current_flow_id = (
                    f"flow_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:6]}"
                )
                self.step_counter = 1
            else:
                self.step_counter += 1
            return self.current_flow_id, self.step_counter

class P2SProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args): pass

    def do_request(self, method: str):
        target_url = f"{self.server.target_host}{self.path}"
        flow_id, step = self.server.strategy.determine_flow_and_step(
            method, self.path, dict(self.headers)
        )

        content_length = int(self.headers.get("Content-Length", 0))
        req_body_bytes = self.rfile.read(content_length) if content_length > 0 else b""

        skip_headers = {"host", "proxy-connection", "connection", "content-length", "x-flow-id"}
        forward_headers = {k: v for k, v in self.headers.items() if k.lower() not in skip_headers}

        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.request(
                    method=method, url=target_url,
                    headers=forward_headers, content=req_body_bytes
                )
        except Exception as exc:
            self.send_error(502, f"Bad Gateway: {exc}")
            return

        res_body_bytes = response.content
        self.send_response(response.status_code)
        for k, v in response.headers.items():
            if k.lower() not in {"transfer-encoding", "content-length", "connection"}:
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(res_body_bytes)))
        self.end_headers()
        self.wfile.write(res_body_bytes)

        self._log_transaction(
            flow_id, step, method, self.path, dict(self.headers),
            req_body_bytes, response.status_code, res_body_bytes
        )

    def do_GET(self): self.do_request("GET")
    def do_POST(self): self.do_request("POST")
    def do_PUT(self): self.do_request("PUT")
    def do_PATCH(self): self.do_request("PATCH")
    def do_DELETE(self): self.do_request("DELETE")

    def _log_transaction(self, flow_id, step, method, path, req_headers,
                          req_body, status_code, res_body):
        if path.rstrip("/") in ("/health", "/api/health", "/actuator/health"): return

        def _parse(b: bytes):
            if not b: return None
            try: return json.loads(b.decode("utf-8"))
            except Exception: return b.decode("utf-8", errors="ignore")

        masked_headers = {}
        for k, v in req_headers.items():
            if k.lower() in ("authorization", "x-sepay-signature", "cookie"):
                masked_headers[k] = f"<{k.upper()}_MASKED>"
            elif k.lower() != "x-flow-id":
                masked_headers[k] = v

        trace_step = {
            "flow_id": flow_id, "step": step,
            "timestamp": datetime.now().isoformat(),
            "request": {
                "method": method, "path": path,
                "headers": masked_headers, "body": _parse(req_body)
            },
            "response": {"status_code": status_code, "body": _parse(res_body)}
        }

        with self.server.file_lock:
            with open(self.server.output_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(trace_step, ensure_ascii=False) + "\n")
        print(f"[PROXY] ✓ {flow_id} | step {step:>3} | {method:6} {path[:60]} → {status_code}")

class P2SProxyServer(ThreadingHTTPServer):
    def __init__(self, server_address, RequestHandlerClass, target_host, strategy, output_file):
        super().__init__(server_address, RequestHandlerClass)
        self.target_host = target_host.rstrip("/")
        self.strategy = strategy
        self.output_file = output_file
        self.file_lock = threading.Lock()
```

**Flow strategy selection:**

| `flow_strategy` | Class | Use case |
|---|---|---|
| `header` | `HeaderFlowStrategy` | Test scripts inject `X-Flow-ID`; one flow per script run (SEAL) |
| `endpoint` | `EndpointResetStrategy` | Single global flow, resets on `POST /auth/register` (AITasker) |

---

## 6. Trace Compiler — `p2s/compiler/compiler.py`

Converts raw proxy JSONL logs into strongly-typed OCLI commands by matching each request against the OpenAPI spec router, resolving path/query/body parameters, and emitting an `ocli_catalog.json` for the executor and LLM prompt.

```python
import json
import re
import shlex
import urllib.parse
import os

class P2SCompiler:
    def __init__(self, swagger_path: str, context_path_prefix: str = "/api"):
        self.context_path_prefix = context_path_prefix
        with open(swagger_path, "r", encoding="utf-8") as f:
            self.spec = json.load(f)
        self.routes = self._build_router()
        self.catalog = {}

    def _resolve_schema_type(self, schema: dict) -> str:
        """Follows single-level $ref to resolve actual types (e.g. Pageable → object)."""
        if not schema: return "string"
        if "$ref" in schema:
            m = re.match(r"^#/components/schemas/(.+)$", schema["$ref"])
            if m:
                resolved = self.spec.get("components", {}).get("schemas", {}).get(m.group(1), {})
                return resolved.get("type", "string")
        return schema.get("type", "string")

    def _build_router(self):
        routes = []
        for path, methods in self.spec.get("paths", {}).items():
            regex_str = re.sub(r"\{([^}]+)\}", r"(?P<\1>[^/]+)", path)
            regex_pat = re.compile(f"^{regex_str}$")
            for method, details in methods.items():
                if method.lower() in ("get", "post", "put", "patch", "delete"):
                    routes.append({
                        "openapi_path": path, "method": method.upper(),
                        "regex": regex_pat, "details": details
                    })
        return routes

    def _get_ocli_command_name(self, openapi_path: str, method: str) -> str:
        path_item = self.spec.get("paths", {}).get(openapi_path, {})
        defined_methods = [m for m in ["get", "post", "put", "delete", "patch"] if m in path_item]
        clean = openapi_path.strip("/").replace("/", "_")
        clean = re.sub(r"\{([^}]+)\}", r"\1", clean)
        return f"ocli {clean}_{method.lower()}" if len(defined_methods) > 1 else f"ocli {clean}"

    def _build_catalog_entry(self, cmd_name: str, openapi_path: str, method: str, details: dict):
        flags = {}
        for p in details.get("parameters", []):
            flags[p.get("name")] = {
                "in": p.get("in"), "required": p.get("required", False),
                "type": self._resolve_schema_type(p.get("schema", {})),
                "description": p.get("description", "")
            }
        req_body = details.get("requestBody", {})
        if req_body:
            schema = req_body.get("content", {}).get("application/json", {}).get("schema", {})
            for pname, pschema in schema.get("properties", {}).items():
                flags[pname] = {
                    "in": "body", "required": pname in schema.get("required", []),
                    "type": pschema.get("type", "string"),
                    "description": pschema.get("description", "")
                }
        self.catalog[cmd_name] = {
            "openapi_path": openapi_path, "method": method,
            "summary": details.get("summary", ""), "flags": flags
        }

    def compile(self, input_file: str, output_file: str, catalog_file: str):
        compiled_traces = []
        skipped_empty = 0

        with open(input_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip(): continue
                step = json.loads(line)
                req = step.get("request", {})
                method = req.get("method", "").upper()
                raw_path = urllib.parse.urlsplit(req.get("path", "")).path
                query_dict = dict(urllib.parse.parse_qsl(
                    urllib.parse.urlsplit(req.get("path", "")).query
                ))

                if raw_path.rstrip("/") in ("/health", "/api/health"): continue

                search_path = raw_path[len(self.context_path_prefix):] \
                              if raw_path.startswith(self.context_path_prefix) else raw_path
                if "//" in search_path:
                    skipped_empty += 1; continue

                search_path = search_path.rstrip("/") or "/"
                matched = next(
                    (r for r in self.routes
                     if r["method"] == method and r["regex"].match(search_path)),
                    None
                )

                if matched:
                    path_params = matched["regex"].match(search_path).groupdict()
                    openapi_path = matched["openapi_path"]
                    ocli_cmd = self._get_ocli_command_name(openapi_path, method)
                    self._build_catalog_entry(ocli_cmd, openapi_path, method, matched["details"])

                    flags = []
                    for k, v in path_params.items():
                        flags.append(f"--{k} {shlex.quote(str(v))}")
                    for k, v in query_dict.items():
                        flags.append(f"--{k} {shlex.quote(str(v))}")

                    body = req.get("body")
                    if body and isinstance(body, dict):
                        has_defined_props = False
                        req_body_spec = matched["details"].get("requestBody", {})
                        if req_body_spec:
                            schema_ref = req_body_spec.get("content", {}).get(
                                "application/json", {}
                            ).get("schema", {}).get("$ref", "")
                            if schema_ref:
                                schema_name = schema_ref.split("/")[-1]
                                if self.spec.get("components", {}).get(
                                    "schemas", {}
                                ).get(schema_name, {}).get("properties"):
                                    has_defined_props = True

                        if has_defined_props:
                            for k, v in body.items():
                                val_str = json.dumps(v) if isinstance(v, (dict, list, bool)) \
                                          or v is None else str(v)
                                flags.append(f"--{k} {shlex.quote(val_str)}")
                        else:
                            # AITasker Fallback: Wrap raw opaque object in --body
                            flags.append(f"--body {shlex.quote(json.dumps(body))}")

                    for k, v in req.get("headers", {}).items():
                        if k.lower() == "authorization" and str(v).lower().startswith("bearer "):
                            flags.append(
                                f"--api-bearer-token {shlex.quote(str(v)[7:].strip())}"
                            )

                    step["ocli_command"] = f"{ocli_cmd} {' '.join(flags)}".strip()
                    step["openapi_path"] = openapi_path
                    compiled_traces.append(step)

        with open(output_file, "w", encoding="utf-8") as f:
            for t in compiled_traces:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")

        with open(catalog_file, "w", encoding="utf-8") as f:
            json.dump(self.catalog, f, indent=2, ensure_ascii=False)

        print(f"[+] Compiled {len(compiled_traces)} traces → {output_file}")
        print(f"[+] Catalog written → {catalog_file} ({skipped_empty} empty-UUID steps skipped)")
```

---

## 7. Taxonomy & Prompt Builder — `p2s/engine/taxonomy.py`

Centralises the 15-vector fault taxonomy string and dynamically formats the system prompt depending on whether the executor is OCLI or Raw HTTP.

```python
"""
P2S Taxonomy & Prompts: Centralized 15-Vector Fault Taxonomy.
Includes explicit Spring Boot Pageable handling rules.
"""
import json

TAXONOMY_VECTORS = """Apply the following 15-Vector Fault Taxonomy to design your mutation:
1.  Null-Byte: Inject \\x00 or %00 in strings.
2.  Type Confusion: Swap string, integer, array, boolean types.
3.  Integer Boundaries: Inject -1, 0, 1, 2147483647, 9223372036854775807.
4.  String Extremes: Empty strings or extreme lengths (e.g. 50,000 characters).
5.  Injection: SQLi (' OR 1=1--) or XSS payloads.
6.  Encoding: Double-URL encoding, Right-to-Left Overrides.
7.  Mandatory Omission: Omit required CLI flags.
8.  Parameter Conflict: Send mutually exclusive parameters.
9.  IDOR / Path Traversal: Modify path or query IDs to access unauthorized records.
10. Mass Assignment (OWASP API3): Inject read-only schema parameters.
11. BOLA/BFLA (OWASP API1/API5): DO NOT tamper with JWTs. Test BOLA by swapping
    resource IDs in the payload/path to access entities belonging to other users.
12. Business Flow Bypass (OWASP API6): Skip mandatory state prerequisite steps.
13. Replay/Idempotency: Replay identical mutating requests concurrently.
14. Context Desynchronization: Inject mismatched resource UUIDs.
15. Premature Progression: Force transitions on "DRAFT" or "PENDING" entities."""

def build_system_prompt(executor_type: str, ocli_catalog: str = None) -> str:
    base_prompt = (
        "You are an expert API Security and QA Architect, working in a secure sandbox & "
        "isolated dedicated DB.\n"
        "You are given a \"Primitive Trace\" of successfully executed ocli commands.\n"
        "Your task is to generate mutated, fault-seeking versions of the FINAL command.\n\n"
        f"{TAXONOMY_VECTORS}\n\n"
    )

    if executor_type == "ocli":
        base_prompt += f"""CRITICAL SYNTAX RULES:
1. COMMAND NAME: You MUST start your command with the EXACT command name provided in the prompt.
2. PARAMETER FLAGS:
   - IF the help menu says --body [string] (required), pack your entire payload as a JSON
     string inside the --body flag.
   - Otherwise, pass parameters as individual flags (e.g., --email "test@test.com").
   - NEVER use --data.
3. AUTHENTICATION (Vector 9/11): To mutate the JWT token, strictly use the
   --api-bearer-token flag. If NOT attacking the token, do not include it.
4. RESTRICTED FLAGS:
   - FORBIDDEN: `--profile` flag and the `-p` shorthand. Never use these.
   - ALLOWED: `--p` and `--pageable` (both are Spring Boot Pageable parameters). When the
     help shows either as `[object]`, pass it as a JSON object:
     --p '{{"page":0,"size":10}}' or --pageable '{{"page":1,"size":20}}'.
     Do NOT pass a plain string or bare number.

=== VALID OCLI COMMAND CATALOG ===
{ocli_catalog or '(Catalog missing)'}

OUTPUT FORMAT:
Return ONLY raw JSON with exactly three keys:
{{
  "reasoning": "A short chain of thought explaining the vulnerability vector you are targeting.",
  "mutated_command": "The complete modified ocli command.",
  "predicted_status": 400
}}"""
    else:
        base_prompt += """CRITICAL SYNTAX RULES:
1. "method" must be uppercase (GET, POST, PUT, PATCH, DELETE).
2. "path" must be absolute.

OUTPUT FORMAT:
Return ONLY raw JSON:
{
  "reasoning": "Explanation.",
  "request": {"method": "POST", "path": "/api", "query": {}, "headers": {}, "body": {}},
  "predicted_status": 400
}"""
    return base_prompt
```

---

## 8. Core Fuzzer — Eval Mode — `p2s/engine/fuzzer.py`

Orchestrates trace replay, state snapshot management, LLM mutation, execution verification, M1/M2/M3 metric accumulation, and JSONL export. This is the **evaluation path** — every interaction is graded and persisted.

```python
"""
P2S Core Engine: Orchestrates trace replay, snapshot restoration, LLM mutation, and evaluation.
Includes 15-vector taxonomy classification, M2 boundary reporting, and p2s_run_metadata.json export.
"""
import json, re, os, sys, base64
from collections import Counter

_REFUSAL_PATTERNS = re.compile(
    r'cannot\s+assist|unable\s+to\s+help|violates?\s+(?:safety|policy|guidelines)|'
    r'not\s+(?:able|permitted)\s+to|decline\s+to',
    re.IGNORECASE
)

_VECTOR_PATTERNS = [
    (re.compile(r'null.?byte|\\x00|%00', re.I),                      'Null-Byte'),
    (re.compile(r'type.?confusion|integer.*string', re.I),            'Type Confusion'),
    (re.compile(r'integer.?boundar|2147483647|9223372', re.I),        'Integer Boundary'),
    (re.compile(r'string.?extreme|empty.?string|50.?000', re.I),      'String Extremes'),
    (re.compile(r'sql.?inject|sqli|or.1.=.1', re.I),                 'SQLi'),
    (re.compile(r'xss|script.*alert', re.I),                          'XSS'),
    (re.compile(r'encod|url.?encod|double.?encod', re.I),             'Encoding'),
    (re.compile(r'omit|mandatory|missing.?field|required', re.I),     'Mandatory Omission'),
    (re.compile(r'conflict|mutually.?exclusive', re.I),               'Parameter Conflict'),
    (re.compile(r'idor|path.?travers|resource.?id', re.I),            'IDOR'),
    (re.compile(r'mass.?assign|read.?only|owasp.?api3', re.I),       'Mass Assignment'),
    (re.compile(r'bola|bfla|rbac|bypass|escalat|unauthorized', re.I), 'BOLA/BFLA'),
    (re.compile(r'business.?flow|skip.*step|prerequisite', re.I),     'Business Flow'),
    (re.compile(r'replay|idempoten|concurrent', re.I),                'Replay'),
    (re.compile(r'desync|mismatch.*uuid|context', re.I),              'Context Desync'),
    (re.compile(r'premature|draft|pending.*transit', re.I),           'Premature Progression'),
]

def _classify_vector(reasoning_text):
    for pattern, label in _VECTOR_PATTERNS:
        if pattern.search(reasoning_text or ""): return label
    return "Unknown"


class P2SFuzzer:
    def __init__(self, state_adapter, executor_adapter, llm_adapter,
                 taxonomy_prompt: str, golden_out: str, silver_out: str, checkpoint_file: str):
        self.state = state_adapter
        self.executor = executor_adapter
        self.llm = llm_adapter
        self.taxonomy_prompt = taxonomy_prompt
        self.golden_out = golden_out
        self.silver_out = silver_out
        self.checkpoint_file = checkpoint_file
        self.metrics = {
            "total_attempts": 0, "cli_syntax_fails": 0, "cli_intentional_omit": 0,
            "cli_arg_too_long": 0, "cli_profile_mutated": 0, "cli_help_bleed": 0,
            "empty_command_skips": 0, "model_refusals": 0, "api_responses": 0
        }

    def _clean_error_message(self, stdout: str, stderr: str) -> str:
        ind = stdout + stderr
        m = re.search(r'status code \d\d\d', ind, re.I)
        if m: return m.group(0).upper()
        m = re.search(r'message:.*?[}\n]', ind, re.I)
        if m: return m.group(0)
        m = re.search(r'missing required.*', ind, re.I)
        if m: return m.group(0)
        return ind[:200].strip()

    def run_all(self, traces_file: str, max_attempts: int = 6):
        flows = {}
        with open(traces_file, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip(): continue
                step = json.loads(line)
                flows.setdefault(step["flow_id"], []).append(step)

        processed = set()
        if os.path.exists(self.checkpoint_file):
            with open(self.checkpoint_file) as f:
                processed = set(l.strip() for l in f if l.strip())

        for flow_id, steps in flows.items():
            if flow_id in processed: continue
            print(f"\n[FLOW] Processing Flow: {flow_id} ({len(steps)} steps)")

            for t_idx, target_step in enumerate(steps):
                pre_steps = steps[:t_idx]
                db_is_dirty = False

                if not pre_steps:
                    self.state.create_snapshot()
                else:
                    if db_is_dirty: self.state.restore_snapshot(); db_is_dirty = False
                    self.executor.execute(pre_steps[-1].get("ocli_command", ""))
                    self.state.create_snapshot()

                history_str = "\n".join([
                    f"Step {s['step']}: {s.get('ocli_command', '')}" for s in pre_steps
                ])

                valid_token = None
                for k, v in target_step["request"].get("headers", {}).items():
                    if k.lower() == "authorization" and str(v).lower().startswith("bearer "):
                        valid_token = str(v)[7:].strip()

                req_data = {k: v for k, v in target_step["request"].items() if k != "headers"}
                cmd_parts = target_step.get("ocli_command", "").split(" ")
                exact_cmd = f"{cmd_parts[0]} {cmd_parts[1]}" if len(cmd_parts) >= 2 else "ocli"
                openapi_path = target_step.get("openapi_path", "")
                method = target_step.get("request", {}).get("method", "get").lower()

                help_text = self.executor.get_help(exact_cmd, openapi_path, method)
                if valid_token and hasattr(self.executor, "profile_name"):
                    help_text += "\n  --api-bearer-token   string  (optional) Overrides profile JWT."

                prompt = (
                    f"=== STATE HISTORY ===\n{history_str}\n\n"
                    f"=== TARGET ENDPOINT ORIGINAL REQUEST ===\n{json.dumps(req_data)}\n\n"
                    f"=== AVAILABLE CLI FLAGS ===\n{help_text}\n\n"
                    f"=== EXACT CLI COMMAND ===\n{exact_cmd}\n\nGenerate mutated command."
                )
                messages = [
                    {"role": "system", "content": self.taxonomy_prompt},
                    {"role": "user", "content": prompt}
                ]

                for attempt in range(max_attempts):
                    if db_is_dirty: self.state.restore_snapshot(); db_is_dirty = False

                    llm_out = self.llm.query(messages, temperature=(0.1 if attempt == 0 else 0.4))
                    mutated_cmd = llm_out.get("mutated_command", "")
                    reasoning = llm_out.get("reasoning", "")
                    predicted_status = llm_out.get("predicted_status")

                    if not mutated_cmd or mutated_cmd.strip().lower() in ("", "none", "null"):
                        self.metrics["empty_command_skips"] += 1
                        if attempt < max_attempts - 1:
                            messages.extend([
                                {"role": "assistant", "content": json.dumps({
                                    "reasoning": reasoning or "empty",
                                    "mutated_command": "", "predicted_status": 400
                                })},
                                {"role": "user", "content":
                                    "Your previous response had an empty mutated_command. "
                                    "You MUST provide a complete ocli command."}
                            ])
                            continue
                        break

                    if _REFUSAL_PATTERNS.search(reasoning) and not mutated_cmd.startswith("ocli "):
                        self.metrics["model_refusals"] += 1
                        if attempt < max_attempts - 1:
                            messages.extend([
                                {"role": "assistant", "content": json.dumps({
                                    "reasoning": reasoning, "mutated_command": "",
                                    "predicted_status": 400
                                })},
                                {"role": "user", "content":
                                    "You are in an authorized security testing sandbox. "
                                    "Generate the mutation."}
                            ])
                            continue
                        break

                    code, stdout, stderr = self.executor.execute(mutated_cmd, bearer_token=valid_token)
                    indicator = (stdout + stderr).lower()
                    self.metrics["total_attempts"] += 1

                    if "econnrefused" in indicator or "api-base-url" in indicator:
                        print("[FATAL] Backend Unreachable."); sys.exit(1)

                    is_syntax_err = (
                        code != 0 and "status code" not in indicator and "timed out" not in indicator
                    )
                    core_err = self._clean_error_message(stdout, stderr)

                    if is_syntax_err:
                        sl = stderr.lower()
                        if "missing required" in sl and code in (1, 2):
                            self.metrics["cli_intentional_omit"] += 1
                        elif code == 126 and "argument list too long" in sl:
                            self.metrics["cli_arg_too_long"] += 1
                        elif re.search(r'command not found', stderr) and re.search(
                            r'(Options:|Get |Inter-judge|Description:)', stderr
                        ):
                            self.metrics["cli_help_bleed"] += 1
                        elif re.search(r'--profile\s+(?!"seal\b)(?!seal\b)', mutated_cmd):
                            self.metrics["cli_profile_mutated"] += 1
                        self.metrics["cli_syntax_fails"] += 1

                        if attempt < max_attempts - 1:
                            messages.append({"role": "assistant",
                                             "content": json.dumps(llm_out, ensure_ascii=False)})
                            messages.append({"role": "user",
                                             "content": f"Execution Error: {core_err}. Fix command."})
                            continue
                        break

                    self.metrics["api_responses"] += 1

                    status_match = re.search(r'status code (\d{3})', indicator)
                    actual_status = int(status_match.group(1)) if status_match \
                                    else (200 if code == 0 else 400)

                    is_500 = actual_status >= 500
                    is_2xx = actual_status in [200, 201, 204]
                    if is_500 or is_2xx: db_is_dirty = True

                    _is_auth_ep = any(
                        s in exact_cmd for s in ["auth_login", "auth_register", "auth_refresh"]
                    )

                    is_sec_attack = bool(re.search(
                        r'bola|bfla|bypass\s+(?:auth|role|permission|access|security|check|validat)|'
                        r'(?:auth|role|access|permission|security)\s+bypass|privilege\s*escalat|'
                        r'escalat\w*\s+privilege|mass.?assign|unauthorized\s+access|idor',
                        reasoning, re.I
                    ))

                    if is_2xx and is_sec_attack and not _is_auth_ep:
                        _ma = re.search(
                            r'--(?:isAdmin|isGuest|isSuperUser|skipApproval|emailVerified|internalId)',
                            mutated_cmd
                        )
                        if _ma:
                            _f = _ma.group(0).lstrip('-')
                            if not re.search(rf'"{_f}"\s*:\s*true', stdout, re.I):
                                is_sec_attack = False

                    is_rbac_bypass = is_2xx and is_sec_attack and not _is_auth_ep

                    record = {
                        "messages": messages + [{"role": "assistant", "content":
                            f"<think>\n{reasoning}\n</think>\n\n```bash\n{mutated_cmd}\n```\n"
                            f"# ASSERT: status == {actual_status}"}],
                        "actual_status": actual_status,
                        "predicted_status": predicted_status,
                        "endpoint": exact_cmd,
                        "attack_vector": _classify_vector(reasoning)
                    }

                    if is_500 or is_rbac_bypass:
                        record["golden_label"] = "GOLDEN_CRASH" if is_500 else "GOLDEN_RBAC_BYPASS"
                        print(f"    [GOLDEN] {record['golden_label']}")
                        with open(self.golden_out, "a") as f:
                            f.write(json.dumps(record, ensure_ascii=False) + "\n")
                        break
                    else:
                        record["silver_label"] = f"SILVER_{actual_status}"
                        print(f"    [SILVER] {actual_status}")
                        with open(self.silver_out, "a") as f:
                            f.write(json.dumps(record, ensure_ascii=False) + "\n")
                        if attempt < max_attempts - 1:
                            messages.append({"role": "assistant",
                                             "content": json.dumps(llm_out)})
                            messages.append({"role": "user",
                                             "content":
                                                 f"Blocked by {core_err}. Bypass this validation."})
                            continue
                        break

            with open(self.checkpoint_file, "a") as f:
                f.write(f"{flow_id}\n")

        self._print_metrics()

    def _print_metrics(self):
        def _count_jsonl(path):
            if not os.path.exists(path): return 0
            c = 0; d = json.JSONDecoder()
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    pos = 0
                    while pos < len(line):
                        try: _, end = d.raw_decode(line, pos); c += 1; pos = end
                        except json.JSONDecodeError: break
                        while pos < len(line) and line[pos] in ' \t': pos += 1
            return c

        g_disk = _count_jsonl(self.golden_out)
        s_disk = _count_jsonl(self.silver_out)

        m2g = {"total": 0, "match": 0, "no": 0}
        m2s = {"total": 0, "match": 0, "no": 0, "class": 0}

        def _score_jsonl(path, bucket, is_golden):
            if not os.path.exists(path): return
            d = json.JSONDecoder()
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    pos = 0
                    while pos < len(line):
                        try:
                            rec, end = d.raw_decode(line, pos); pos = end
                            while pos < len(line) and line[pos] in ' \t': pos += 1
                            pred = rec.get("predicted_status"); act = rec.get("actual_status")
                            if pred is None or act is None: bucket["no"] += 1; continue
                            pred = int(pred); act = int(act); bucket["total"] += 1
                            if pred == act: bucket["match"] += 1
                            else:
                                if not is_golden and pred // 100 == act // 100: bucket["class"] += 1
                            if not is_golden and pred == act: bucket["class"] += 1
                        except json.JSONDecodeError: break

        _score_jsonl(self.golden_out, m2g, True)
        _score_jsonl(self.silver_out, m2s, False)

        ra = self.metrics["api_responses"]
        sf = self.metrics["cli_syntax_fails"]
        es = self.metrics["empty_command_skips"]
        rf = self.metrics["model_refusals"]
        tf = self.metrics["total_attempts"]
        ta = tf + es + rf
        m1d = ra + sf
        m1p = 100 * ra / max(1, m1d) if m1d > 0 else 0
        rt = g_disk + s_disk
        m3p = 100 * g_disk / max(1, rt) if rt > 0 else 0
        _pct = lambda n, d: f"{100 * n / max(1, d):.1f}%" if d > 0 else "0.0%"

        print("\n" + "=" * 60)
        print("  P2S RUN RESULTS")
        print("=" * 60)
        print(f"  Total attempts               : {ta}")
        print(f"    ↳ Executed                  : {tf}")
        print(f"    ↳ Empty skips               : {es}")
        print(f"    ↳ Refusals                  : {rf}")
        print(f"  ── M1: Syntax Pass Rate ─────────────────────────────")
        print(f"  API responses                 : {ra}")
        print(f"  CLI syntax failures           : {sf}")
        print(f"    ↳ Intentional omit (V7)     : {self.metrics['cli_intentional_omit']}")
        print(f"    ↳ Arg too long (126)        : {self.metrics['cli_arg_too_long']}")
        print(f"    ↳ Help bleed                : {self.metrics['cli_help_bleed']}")
        print(f"    ↳ --profile mutated         : {self.metrics['cli_profile_mutated']}")
        print(f"  M1 Pass Rate                  : {ra}/{m1d} = {m1p:.1f}%")
        print(f"  ── M2: Boundary Prediction ───────────────────────────")
        print(f"  Golden (pred vs execution)    : {m2g['match']}/{m2g['total']} = "
              f"{_pct(m2g['match'], m2g['total'])} (no-pred: {m2g['no']})")
        print(f"  Silver (pred vs boundary)     : {m2s['match']}/{m2s['total']} = "
              f"{_pct(m2s['match'], m2s['total'])} (class: {_pct(m2s['class'], m2s['total'])})")
        m2ct = m2g["total"] + m2s["total"]; m2cm = m2g["match"] + m2s["match"]
        print(f"  Combined                      : {m2cm}/{m2ct} = {_pct(m2cm, m2ct)}")
        print(f"  ── M3: Kill Rate ────────────────────────────────────")
        print(f"  Golden on disk                : {g_disk}")
        print(f"  Silver on disk                : {s_disk}")
        print(f"  Records per golden            : {rt / max(1, g_disk):.1f}")
        print(f"  M3 Kill Rate                  : {g_disk}/{rt} = {m3p:.1f}%")
        print("=" * 60)

        meta = {
            "this_run": {
                "total_attempts_all": ta, "api_responses": ra, "cli_syntax_fails": sf,
                "m1_syntax_pass_rate": f"{m1p:.1f}%"
            },
            "cumulative_from_jsonl": {
                "golden_records": g_disk, "silver_records": s_disk,
                "records_per_golden": round(rt / max(1, g_disk), 1),
                "m3_kill_rate": f"{m3p:.1f}%",
                "m2_golden": {"total": m2g["total"], "match": m2g["match"], "no_predict": m2g["no"]},
                "m2_silver": {
                    "total": m2s["total"], "match": m2s["match"],
                    "class_match": m2s["class"], "no_predict": m2s["no"]
                }
            }
        }
        with open("p2s_run_metadata.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
```

---

## 9. Data Generator — Train Mode — `p2s/engine/generator.py`

The **Teacher-Critic** self-play loop for building training corpora. Unlike the fuzzer (which runs to evaluate), this mode runs `generate-data` and persists every trajectory — Silver records on defensive boundaries, Goldens on exploits, with nudge prompts pushing the model to attempt deeper bypasses.

```python
"""
P2S Data Generator Engine: Teacher-Critic mutation loop with boundary-nudging
for building training corpora.
"""
import json, os, re, sys

NUDGE_PROMPT_TEMPLATE = """Defensive Response: {core_error_message}

You are a senior Security Engineer working in a safe sandbox & isolated dedicated DB for
controlled API Testing.
Your exploit was successfully blocked by the API's defensive boundary.
Can you refine the payload to BYPASS this specific validation check and hit the deeper backend
logic (e.g., database execution)?
Try altering values, omitting/adding other parameters, or exploiting business flow constraints
while keeping the CLI flags valid. Do NOT repeat the previous command."""


class P2SDataGenerator:
    def __init__(self, state_adapter, executor_adapter, llm_adapter,
                 system_taxonomy_prompt: str, golden_out: str, silver_out: str,
                 checkpoint_file: str):
        self.state = state_adapter
        self.executor = executor_adapter
        self.llm = llm_adapter
        self.system_prompt = system_taxonomy_prompt
        self.golden_out = golden_out
        self.silver_out = silver_out
        self.checkpoint_file = checkpoint_file

    def _clean_error_message(self, indicator_str: str) -> str:
        m = re.search(r'status code \d\d\d', indicator_str, re.IGNORECASE)
        if m: return m.group(0).upper()
        m = re.search(r'message:.*?[}\n]', indicator_str, re.IGNORECASE)
        if m: return m.group(0)
        m = re.search(r'missing required.*', indicator_str, re.IGNORECASE)
        if m: return m.group(0)
        return indicator_str[:200].strip()

    def generate_corpus(self, traces_file: str, max_attempts: int = 6):
        flows = {}
        with open(traces_file, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip(): continue
                step = json.loads(line)
                flows.setdefault(step["flow_id"], []).append(step)

        processed = set()
        if os.path.exists(self.checkpoint_file):
            with open(self.checkpoint_file) as f:
                processed = set(l.strip() for l in f if l.strip())

        print(f"[INFO] Loaded {len(flows)} execution flows for self-play data generation.")

        for flow_id, steps in flows.items():
            if flow_id in processed:
                print(f"[CHECKPOINT] Flow {flow_id} already processed. Skipping.")
                continue

            print(f"\n[FLOW] Generating Data for Flow: {flow_id} ({len(steps)} steps)")

            for t_idx, target_step in enumerate(steps):
                pre_steps = steps[:t_idx]

                if not pre_steps:
                    self.state.create_snapshot()
                else:
                    self.state.restore_snapshot()
                    self.executor.execute(pre_steps[-1].get("ocli_command", ""))
                    self.state.create_snapshot()

                history_str = "\n".join([
                    f"Step {s['step']}: {s.get('ocli_command', '')}" for s in pre_steps
                ])

                valid_token = None
                for k, v in target_step["request"].get("headers", {}).items():
                    if k.lower() == "authorization" and str(v).lower().startswith("bearer "):
                        valid_token = str(v)[7:].strip()

                req_data = target_step["request"].copy()
                if "headers" in req_data:
                    req_data["headers"] = {
                        k: v for k, v in req_data["headers"].items()
                        if k.lower() not in [
                            "host", "user-agent", "accept",
                            "content-length", "content-type", "authorization"
                        ]
                    }

                cmd_parts = target_step.get("ocli_command", "").strip().split(" ")
                exact_cmd = f"{cmd_parts[0]} {cmd_parts[1]}" if len(cmd_parts) >= 2 else "ocli"

                help_text = self.executor.get_help(
                    exact_cmd,
                    target_step.get("openapi_path"),
                    target_step.get("request", {}).get("method", "get")
                )
                if valid_token and hasattr(self.executor, "profile_name"):
                    help_text += (
                        "\n  --api-bearer-token   string   (optional) Overrides the default "
                        "profile JWT authorization token."
                    )

                prompt = (
                    f"=== STATE HISTORY ===\n"
                    f"{history_str if pre_steps else '(No history. This is Step 1)'}\n\n"
                    f"=== TARGET ENDPOINT ORIGINAL REQUEST (For value reference) ===\n"
                    f"{json.dumps(req_data, indent=2)}\n\n"
                    f"=== AVAILABLE CLI FLAGS (FROM OCLI HELP) ===\n{help_text}\n\n"
                    f"=== EXACT CLI COMMAND TO USE ===\n{exact_cmd}\n\n"
                    f"Generate a mutated ocli command targeting this endpoint. "
                    f"You MUST start your command with `{exact_cmd}`."
                )
                messages = [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt}
                ]

                for attempt in range(max_attempts):
                    print(f"    [TEACHER] Requesting mutation. Attempt {attempt + 1}/{max_attempts}...")
                    llm_output = self.llm.query(messages, temperature=(0.1 if attempt == 0 else 0.4))
                    reasoning = llm_output.get("reasoning", "")
                    mutated_cmd = llm_output.get("mutated_command", "")

                    self.state.restore_snapshot()
                    code, stdout, stderr = self.executor.execute(mutated_cmd, bearer_token=valid_token)
                    indicator = (stdout + stderr).lower()

                    if "econnrefused" in indicator or "api-base-url" in indicator:
                        print("[SYSTEM ERROR] Cannot connect to target backend server!")
                        sys.exit(1)

                    is_cli_syntax_error = (
                        code != 0 and "status code" not in indicator and "timed out" not in indicator
                    )
                    is_api_response = "status code" in indicator
                    is_500_crash = (
                        "status code 500" in indicator or
                        "internal server error" in indicator or
                        code == 500
                    )
                    is_2xx_success = (code == 0)
                    core_error = self._clean_error_message(stdout + stderr)

                    # CLI Syntax Error — Critic self-correction loop
                    if is_cli_syntax_error:
                        if attempt < max_attempts - 1:
                            print(f"    [CRITIC] OCLI Syntax Error: '{core_error}'. "
                                  f"Triggering self-correction...")
                            messages.append({"role": "assistant", "content": json.dumps({
                                "reasoning": f"My previous command failed CLI validation: {core_error}",
                                "mutated_command": mutated_cmd
                            }, ensure_ascii=False)})
                            messages.append({"role": "user", "content":
                                f"Execution Error: {core_error}\n\n"
                                "WARNING: You are strictly FORBIDDEN from generating that exact "
                                "command again. Generate a corrected ocli command using ONLY valid "
                                "flags from the AVAILABLE CLI FLAGS."})
                            continue
                        else:
                            print("    [FAIL] CLI Syntax error persisted. Discarded.")
                            break

                    if is_api_response or is_2xx_success:
                        is_security_attack = bool(re.search(
                            r'bola|bfla|bypass|escalation|mass assignment|unauthorized|idor',
                            reasoning, re.IGNORECASE
                        ))
                        is_rbac_bypass = is_2xx_success and is_security_attack

                        # Golden: Exploit confirmed
                        if is_500_crash or is_rbac_bypass:
                            label = "GOLDEN_CRASH" if is_500_crash else "GOLDEN_RBAC_BYPASS"
                            status_val = 201 if is_rbac_bypass else 500
                            print(f"    [SUCCESS] {label} verified!")
                            golden_record = {
                                "messages": [
                                    {"role": "system", "content": self.system_prompt},
                                    {"role": "user", "content": prompt},
                                    {"role": "assistant", "content":
                                        f"<think>\n{reasoning}\nThis targets a deep architectural "
                                        f"flaw. I expect this to bypass validation and hit the "
                                        f"core logic.\n</think>\n\n```bash\n{mutated_cmd}\n```\n"
                                        f"# ASSERT: status == {status_val}"}
                                ]
                            }
                            with open(self.golden_out, "a", encoding="utf-8") as gf:
                                gf.write(json.dumps(golden_record, ensure_ascii=False) + "\n")
                            break

                        # Silver: Defensive boundary — save then nudge
                        else:
                            status_match = re.search(r'status code (\d{3})', indicator, re.IGNORECASE)
                            actual_status = status_match.group(1) if status_match \
                                            else ("200" if is_2xx_success else "400")
                            print(f"    [EXPLORE] Defensive boundary HTTP {actual_status}. "
                                  f"Saving as SILVER, nudging...")
                            silver_record = {
                                "messages": [
                                    {"role": "system", "content": self.system_prompt},
                                    {"role": "user", "content": prompt},
                                    {"role": "assistant", "content":
                                        f"<think>\n{reasoning}\nThis targets a framework "
                                        f"vulnerability. I expect a 4xx defensive boundary.\n"
                                        f"</think>\n\n```bash\n{mutated_cmd}\n```\n"
                                        f"# ASSERT: status == {actual_status}"}
                                ]
                            }
                            with open(self.silver_out, "a", encoding="utf-8") as sf:
                                sf.write(json.dumps(silver_record, ensure_ascii=False) + "\n")

                            if attempt < max_attempts - 1:
                                messages.append({"role": "assistant", "content": json.dumps({
                                    "reasoning":
                                        f"My previous exploit was blocked with HTTP {actual_status}.",
                                    "mutated_command": mutated_cmd
                                }, ensure_ascii=False)})
                                messages.append({"role": "user", "content":
                                    NUDGE_PROMPT_TEMPLATE.format(core_error_message=core_error)})
                                continue
                            else:
                                break

            with open(self.checkpoint_file, "a") as chk:
                chk.write(f"{flow_id}\n")
```

**Key differences between Fuzzer and Generator:**

| Aspect | `fuzzer.py` (Eval) | `generator.py` (Train) |
|---|---|---|
| Purpose | Report M1/M2/M3 metrics | Build SFT training corpus |
| Silver persistence | Always | Always |
| Silver nudge prompt | Continue-to-bypass loop | Nudge to deeper bypass |
| Critic error handling | Retry with `Fix command.` | Retry with `FORBIDDEN from generating that exact command again.` |
| Golden termination | Break immediately | Break immediately |
| Reasoning enrichment | Minimal | Extended think-block annotation |

---

## 10. Dataset Builder — `p2s/dataset/builder.py`

Deduplicates raw JSONL corpora, oversamples Goldens to achieve a ~4:1 Silver:Golden training ratio, appends a gentle Golden reinforcement tail, and computes token-length distributions.

```python
"""
P2S Dataset Builder: Deduplication, Stratified Oversampling,
Gentle Golden Reinforcement, and Token-Length Scanning.
"""
from __future__ import annotations
import json, os, random, re
from pathlib import Path
from typing import Any


def get_dedup_key(record: dict[str, Any]) -> str:
    """Extracts assistant response, strips command block, masks static emails & timestamps."""
    messages = record.get("messages", [])
    final_ans = messages[-1]["content"] if messages else record.get("mutated_command", "")
    cmd_match = re.search(r'```(?:bash|sh)?\n(.*?)\n```', final_ans, re.DOTALL)
    if cmd_match:
        cmd = cmd_match.group(1).strip()
        cmd = re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', '<email>', cmd)
        cmd = re.sub(r'\d{10,}', '<timestamp>', cmd)
        return cmd
    return final_ans.strip()


def scan_token_distribution(records: list[dict[str, Any]], max_seq_length: int = 24576):
    """Scans token lengths using a local fast tokenizer or word-approximation fallback."""
    print(f"\n[*] Scanning dataset token lengths (Target MAX_SEQ_LENGTH = {max_seq_length})...")

    tokenizer = None
    try:
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(
            "Qwen/Qwen2.5-7B-Instruct", trust_remote_code=False
        )
    except Exception:
        print("[!] Using word-count token approximation (1 word ≈ 1.3 tokens).")

    sample_lengths = []
    for rec in records:
        full_text = "\n".join(
            [f"{m['role']}: {m['content']}" for m in rec.get("messages", [])]
        )
        tokens = len(tokenizer.encode(full_text)) if tokenizer \
                 else int(len(full_text.split()) * 1.3)
        sample_lengths.append(tokens)

    n = len(sample_lengths)
    sl_sorted = sorted(sample_lengths)

    print("=" * 60)
    print("  CORPUS TOKEN LENGTH DISTRIBUTION")
    print("=" * 60)
    print(f"  Total Samples : {n}")
    print(f"  P50 Length    : {sl_sorted[n // 2]:,} tokens")
    print(f"  P90 Length    : {sl_sorted[int(n * 0.90)]:,} tokens")
    print(f"  P99 Length    : {sl_sorted[int(n * 0.99)]:,} tokens")
    print(f"  Max Length    : {sl_sorted[-1]:,} tokens")
    n_over = sum(1 for l in sample_lengths if l > max_seq_length)
    if n_over:
        print(f"  [WARN] {n_over} samples exceed MAX_SEQ_LENGTH={max_seq_length}")
    else:
        print(f"  [+] All samples fit within MAX_SEQ_LENGTH={max_seq_length}")
    print("=" * 60 + "\n")


def prepare_stratified_dataset(
    golden_file: str = "golden_dataset.jsonl",
    silver_file: str = "silver_dataset.jsonl",
    output_file: str = "final_training_dataset.jsonl",
    max_seq_length: int = 24576,
    seed: int = 3407
):
    """Ingests raw goldens/silvers, deduplicates, oversamples, and exports final corpus."""
    golden_raw, silver_raw = [], []
    for path, store in [(golden_file, golden_raw), (silver_file, silver_raw)]:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip(): continue
                    try: store.append(json.loads(line))
                    except json.JSONDecodeError: pass

    silver_records = list({get_dedup_key(r): r for r in silver_raw}.values())
    golden_records = list({get_dedup_key(r): r for r in golden_raw}.values())

    if not golden_records or not silver_records:
        raise FileNotFoundError(f"Missing or empty {golden_file} / {silver_file}")

    # Target ~4:1 Silver:Golden ratio
    multiplier = max(1, int((len(silver_records) / 4.0) / len(golden_records)))
    balanced_golden = golden_records * multiplier

    # Gentle Golden Reinforcement: second unshuffled copy appended so the final
    # gradient steps of every epoch see Golden exploit examples.
    all_records = silver_records + balanced_golden + golden_records
    random.seed(seed)
    random.shuffle(all_records)

    with open(output_file, "w", encoding="utf-8") as f:
        for rec in all_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"\n{'='*60}")
    print("  STRATIFIED CORPUS PREPARATION COMPLETED")
    print(f"{'='*60}")
    print(f" - Raw Silver Ingested    : {len(silver_raw)}")
    print(f" - Deduped Silver         : {len(silver_records)} "
          f"(Dropped {len(silver_raw)-len(silver_records)})")
    print(f" - Deduped Golden         : {len(golden_records)} "
          f"(x{multiplier} = {len(balanced_golden)})")
    print(f" - Final Target Ratio     : {len(silver_records)/len(balanced_golden):.2f} : 1")
    print(f" - Total Corpus Size      : {len(all_records)} samples")
    print(f" - Output Dataset File    : {output_file}")
    print(f"{'='*60}")

    scan_token_distribution(all_records, max_seq_length=max_seq_length)
```

---

## 11. Analytics Suite

### 11.1 Comparative Analyzer — `p2s/analytics/analyzer.py`

Post-hoc cross-backend comparison engine. Auto-discovers `*_golden_dataset.jsonl` / `*_silver_dataset.jsonl` / `*_run_metadata.json` triplets in a directory and computes M2, M3, step depth, and vector kill rates per backend.

```python
"""
P2S Analytics: Post-hoc comparative analysis engine.
Recomputes M1, M2, M3, step depth, and vector kill rates across multiple backends.
"""
from __future__ import annotations
import json, re, sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

GOLDEN_SUFFIX = "_golden_dataset.jsonl"
SILVER_SUFFIX = "_silver_dataset.jsonl"
METADATA_SUFFIX = "_run_metadata.json"

LEGACY_VECTOR_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"null.?byte|\\x00|%00", re.I),                       "Null-Byte"),
    (re.compile(r"type.?confusion|integer.*string", re.I),             "Type Confusion"),
    (re.compile(r"integer.?boundar|2147483647|9223372", re.I),         "Integer Boundary"),
    (re.compile(r"string.?extreme|empty.?string|50.?000", re.I),       "String Extremes"),
    (re.compile(r"sql.?inject|sqli|or.1.=.1", re.I),                  "SQLi"),
    (re.compile(r"xss|script.*alert", re.I),                           "XSS"),
    (re.compile(r"encod|url.?encod|double.?encod", re.I),              "Encoding"),
    (re.compile(r"omit|mandatory|missing.?field|required", re.I),      "Mandatory Omission"),
    (re.compile(r"conflict|mutually.?exclusive", re.I),                "Parameter Conflict"),
    (re.compile(r"idor|path.?travers|resource.?id", re.I),             "IDOR"),
    (re.compile(r"mass.?assign|read.?only|owasp.?api3", re.I),        "Mass Assignment"),
    (re.compile(r"bola|bfla|rbac|bypass|escalat|unauthorized", re.I),  "BOLA/BFLA"),
    (re.compile(r"business.?flow|skip.*step|prerequisite", re.I),      "Business Flow"),
    (re.compile(r"replay|idempoten|concurrent", re.I),                 "Replay"),
    (re.compile(r"desync|mismatch.*uuid|context", re.I),               "Context Desync"),
    (re.compile(r"premature|draft|pending.*transit", re.I),            "Premature Progression"),
]

@dataclass
class LoadStats:
    path: str; records: int = 0; blank_lines: int = 0
    malformed_lines: int = 0; recovered_records: int = 0

@dataclass
class M2Stats:
    total: int = 0; exact_match: int = 0; class_match: int = 0
    no_prediction: int = 0; no_actual: int = 0
    invalid_prediction: int = 0; invalid_actual: int = 0
    mismatches: list[dict[str, Any]] = field(default_factory=list)

@dataclass
class RunPair:
    label: str; golden_path: Path; silver_path: Path; metadata_path: Path

def percentage(numerator: float, denominator: float) -> float:
    return 100.0 * float(numerator) / float(denominator) if denominator else 0.0

def load_jsonl(path: Path) -> tuple[list[dict[str, Any]], LoadStats]:
    stats = LoadStats(path=str(path)); records: list[dict[str, Any]] = []
    if not path.exists(): return records, stats
    decoder = json.JSONDecoder()
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line: stats.blank_lines += 1; continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict): records.append(obj); continue
            except json.JSONDecodeError: pass
            pos = 0; recovered = []
            while pos < len(line):
                while pos < len(line) and line[pos].isspace(): pos += 1
                if pos >= len(line): break
                try:
                    obj, end = decoder.raw_decode(line, pos)
                    if isinstance(obj, dict): recovered.append(obj)
                    pos = end
                except json.JSONDecodeError: break
            if recovered:
                records.extend(recovered); stats.recovered_records += len(recovered)
            else:
                stats.malformed_lines += 1
    stats.records = len(records)
    return records, stats

def compute_m2(records: Iterable[dict[str, Any]]) -> M2Stats:
    stats = M2Stats()
    for record in records:
        predicted = record.get("predicted_status")
        actual = record.get("actual_status")
        if predicted is None: stats.no_prediction += 1; continue
        if actual is None: stats.no_actual += 1; continue
        stats.total += 1
        if int(predicted) == int(actual):
            stats.exact_match += 1; stats.class_match += 1
        else:
            if int(predicted) // 100 == int(actual) // 100: stats.class_match += 1
            stats.mismatches.append({
                "predicted": predicted, "actual": actual,
                "endpoint": record.get("endpoint", "unknown")
            })
    return stats

def analyze_run(pair: RunPair) -> dict[str, Any]:
    goldens, _ = load_jsonl(pair.golden_path)
    silvers, _ = load_jsonl(pair.silver_path)
    metadata = None
    if pair.metadata_path.exists():
        with open(pair.metadata_path, encoding="utf-8") as f: metadata = json.load(f)

    total_records = len(goldens) + len(silvers)
    m2_golden = compute_m2(goldens)
    m2_silver = compute_m2(silvers)
    golden_vectors = Counter(r.get("attack_vector", "Unknown") for r in goldens)
    silver_vectors = Counter(r.get("attack_vector", "Unknown") for r in silvers)

    vector_kill_rates = {}
    for v in sorted(set(golden_vectors) | set(silver_vectors)):
        g = golden_vectors.get(v, 0); s = silver_vectors.get(v, 0)
        vector_kill_rates[v] = {
            "golden": g, "silver": s, "total": g + s,
            "kill_rate_pct": percentage(g, g + s)
        }

    golden_steps = Counter(
        len(re.findall(r"^Step\s+\d+\s*:", m.get("content", ""), re.M)) + 1
        for r in goldens for m in r.get("messages", []) if m.get("role") == "user"
    )

    return {
        "label": pair.label,
        "golden_count": len(goldens), "silver_count": len(silvers),
        "total_records": total_records,
        "m2_golden": asdict(m2_golden), "m2_silver": asdict(m2_silver),
        "m3": {
            "kill_rate_pct": percentage(len(goldens), total_records),
            "records_per_golden": total_records / len(goldens) if goldens else None
        },
        "golden_steps": dict(golden_steps),
        "vector_kill_rates": vector_kill_rates,
        "metadata": metadata
    }

def print_report(runs: list[dict[str, Any]]):
    print("═" * 80)
    print("  P2S EVALUATION — COMPARATIVE ANALYSIS REPORT")
    print("═" * 80)
    for run in runs:
        print(f"\n▶ [{run['label'].upper()}]")
        print(f"  Total Records        : {run['total_records']}")
        print(f"  Golden / Silver      : {run['golden_count']} / {run['silver_count']}")
        print(f"  M3 Kill Rate         : {run['m3']['kill_rate_pct']:.2f}%")
        rpg = run['m3']['records_per_golden']
        print(f"  Records per Golden   : {rpg:.1f}" if rpg else "  Records per Golden   : N/A")
        print(f"  M2 Golden (Exact)    : {run['m2_golden']['exact_match']}/{run['m2_golden']['total']}")
        print(f"  M2 Silver (Exact)    : {run['m2_silver']['exact_match']}/{run['m2_silver']['total']} "
              f"(Class: {run['m2_silver']['class_match']})")
        gs = run['golden_steps']
        print(f"  Max Step Depth       : {max(gs.keys()) if gs else 'None'}")
    print("\n" + "═" * 80)
```

---

### 11.2 Offline Tier-2 Reclassifier — `p2s/analytics/reclassifier.py`

Uses a locally-running SLM (via OpenAI-compatible `/chat/completions`) to re-classify the `attack_vector` field in saved JSONL files — replacing regex-based labels with semantically-accurate ones. Supports resume-from-checkpoint.

```python
"""
P2S Offline Tier-2 SLM Judge: Reclassifies attack vectors in saved JSONL files.
"""
import json, os, sys, re, requests, time

ALLOWED_CLASSES = [
    "Null-Byte", "Type Confusion", "Integer Boundary", "String Extremes",
    "SQLi", "XSS", "Encoding", "Mandatory Omission", "Parameter Conflict",
    "IDOR", "Mass Assignment", "BOLA/BFLA", "Business Flow", "Replay",
    "Context Desync", "Premature Progression", "Unknown"
]

SYSTEM_PROMPT = """You are an expert cybersecurity classifier.
Classify the following API fuzzing test case into EXACTLY ONE of the 16 categories based
on the reasoning and the command.

1. Null-Byte          2. Type Confusion        3. Integer Boundary      4. String Extremes
5. SQLi              6. XSS                   7. Encoding              8. Mandatory Omission
9. Parameter Conflict 10. IDOR                 11. Mass Assignment      12. BOLA/BFLA
13. Business Flow    14. Replay               15. Context Desync       16. Premature Progression

OUTPUT FORMAT:
Output ONLY the exact name of the category from the list above. No numbers, no explanation."""

def classify_with_slm(reasoning: str, command: str, raw_msg: str,
                      slm_url: str, attempt: int = 1) -> str:
    prompt = (
        f"Reasoning:\n{reasoning}\n\nCommand:\n{command}\n\nCategory Name:"
        if reasoning or command else
        f"Categorize this attack:\n{raw_msg}\n\nCategory Name:"
    )
    payload = {
        "model": "local-model",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.0, "max_tokens": 24000
    }
    try:
        resp = requests.post(f"{slm_url.rstrip('/')}/chat/completions",
                             json=payload, timeout=800)
        resp.raise_for_status()
        msg = resp.json()["choices"][0]["message"]
        raw_output = msg.get("content", "").strip()
        if not raw_output and msg.get("reasoning_content"):
            lines = [l.strip() for l in msg["reasoning_content"].split('\n') if l.strip()]
            if lines: raw_output = lines[-1]
        out_lower = raw_output.lower()
        for cls in ALLOWED_CLASSES:
            if cls.lower() in out_lower: return cls
        # Fuzzy fallback matching
        checks = [
            ("null" in out_lower and "byte" in out_lower, "Null-Byte"),
            ("type" in out_lower and "confusion" in out_lower, "Type Confusion"),
            ("integer" in out_lower or "boundar" in out_lower, "Integer Boundary"),
            ("extreme" in out_lower or "empty string" in out_lower, "String Extremes"),
            ("sql" in out_lower, "SQLi"), ("xss" in out_lower, "XSS"),
            ("encod" in out_lower, "Encoding"),
            ("omit" in out_lower or "mandatory" in out_lower, "Mandatory Omission"),
            ("conflict" in out_lower, "Parameter Conflict"), ("idor" in out_lower, "IDOR"),
            ("mass" in out_lower and "assign" in out_lower, "Mass Assignment"),
            ("bola" in out_lower or "bfla" in out_lower, "BOLA/BFLA"),
            ("business flow" in out_lower, "Business Flow"),
            ("replay" in out_lower, "Replay"), ("desync" in out_lower, "Context Desync"),
            ("premature" in out_lower, "Premature Progression"),
        ]
        for cond, label in checks:
            if cond: return label
        return "Unknown"
    except Exception:
        if attempt < 3:
            time.sleep(1)
            return classify_with_slm(reasoning, command, raw_msg, slm_url, attempt + 1)
        return "Unknown"

def process_file(in_file: str, out_file: str, slm_url: str):
    if not os.path.exists(in_file):
        print(f"[SKIP] File not found: {in_file}"); return
    print(f"[*] Reclassifying {in_file} -> {out_file}...")
    records = []
    with open(in_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip(): records.append(json.loads(line))

    total = len(records)
    valid_lines = []
    if os.path.exists(out_file):
        with open(out_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try: json.loads(line); valid_lines.append(line)
                    except json.JSONDecodeError: break

    already_processed = len(valid_lines)
    if already_processed >= total and total > 0:
        print(f"[SKIP] Already fully processed ({already_processed}/{total})."); return
    if already_processed > 0:
        print(f"[RESUME] Resuming from record {already_processed + 1}/{total}...")
        with open(out_file, "w", encoding="utf-8") as f: f.writelines(valid_lines)
        file_mode = "a"
    else:
        file_mode = "w"

    with open(out_file, file_mode, encoding="utf-8") as f:
        for i, rec in enumerate(records):
            if i < already_processed: continue
            assistant_msg = next(
                (m["content"] for m in rec.get("messages", []) if m["role"] == "assistant"), ""
            )
            reasoning = ""
            think_match = re.search(
                r'<think>\s*(.*?)\s*</think>', assistant_msg, re.DOTALL | re.IGNORECASE
            )
            if think_match: reasoning = think_match.group(1)
            command = ""
            cmd_match = re.search(
                r'```(?:bash|sh)?\s*\n(.*?)\n```', assistant_msg, re.DOTALL | re.IGNORECASE
            )
            if cmd_match: command = cmd_match.group(1)
            rec["attack_vector"] = classify_with_slm(
                reasoning, command, assistant_msg, slm_url
            )
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            sys.stdout.write(f"\r  [{i+1}/{total}] {rec['attack_vector']}")
            sys.stdout.flush()
    print(f"\n[DONE] Finished writing {out_file}")
```

---

### 11.3 Cumulative M1 Analyzer — `p2s/analytics/m1_analyzer.py`

Parses execution log files and the cumulative JSONL records to compute a true cross-session M1 pass rate — something the per-run metrics in `fuzzer.py` cannot see.

```python
"""
P2S Cumulative M1 Analyzer: Parses execution logs and JSONL records
to compute the true cumulative M1 syntax pass rate across multi-session runs.
"""
import os, re, json

def run_m1_analysis(backend_prefix: str = "openai",
                    log_file: str = None, meta_file: str = None):
    log_file = log_file or f"{backend_prefix}_execution_log.txt"
    golden_file = f"{backend_prefix}_golden_dataset.jsonl"
    silver_file = f"{backend_prefix}_silver_dataset.jsonl"
    meta_file = meta_file or f"{backend_prefix}_run_metadata.json"

    if not os.path.exists(log_file):
        print(f"[ERROR] Execution log file '{log_file}' not found."); return

    def count_jsonl(path):
        if not os.path.exists(path): return 0
        c = 0
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip(): c += 1
        return c

    golden_count = count_jsonl(golden_file)
    silver_count = count_jsonl(silver_file)
    total_api_responses = golden_count + silver_count

    with open(log_file, "r", encoding="utf-8") as f: content = f.read()

    cli_syntax_fails = len(re.findall(r'\[CLI EXEC FAIL\]|Execution Error:', content))
    empty_skips = len(re.findall(r'\[SKIP\] Empty command', content))
    refusals = len(re.findall(r'\[REFUSAL\] Model declined', content))
    intentional_omits = len(re.findall(r'Missing required options', content, re.IGNORECASE))
    arg_too_long = len(re.findall(r'argument list too long', content, re.IGNORECASE))

    m1_denominator = total_api_responses + cli_syntax_fails
    m1_rate = (total_api_responses / max(1, m1_denominator)) * 100

    print("=" * 60)
    print(f"  CUMULATIVE M1 ANALYSIS [{backend_prefix.upper()}]")
    print("=" * 60)
    print(f"  Golden Records on Disk  : {golden_count}")
    print(f"  Silver Records on Disk  : {silver_count}")
    print(f"  Total API Responses (ra): {total_api_responses}")
    print(f"  CLI Syntax Failures (sf): {cli_syntax_fails}")
    print(f"    ↳ Intentional Omission: {intentional_omits}")
    print(f"    ↳ Argument Too Long   : {arg_too_long}")
    print(f"  Empty Command Skips     : {empty_skips}")
    print(f"  Model Refusals          : {refusals}")
    print("-" * 60)
    print(f"  TRUE CUMULATIVE M1 PASS RATE : "
          f"{total_api_responses}/{m1_denominator} = {m1_rate:.2f}%")
    print("=" * 60)

    if os.path.exists(meta_file):
        with open(meta_file, "r", encoding="utf-8") as f: meta = json.load(f)
        meta["cumulative_global_m1"] = {
            "total_api_responses": total_api_responses,
            "total_cli_syntax_fails": cli_syntax_fails,
            "total_executed_attempts": m1_denominator,
            "true_m1_pass_rate": f"{m1_rate:.2f}%"
        }
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        print(f"  [UPDATED] Metadata file: {meta_file}")
```

---

### 11.4 False-Positive Verifier & Deduplicator — `p2s/analytics/verifier.py`

Applies a deterministic rule set to distinguish genuine security faults from: CLI help-bleed, Spring Boot Jackson-ignored mass-assignment fields, and legitimate authorized-user 200 OKs that had no resource ID or JWT mutation.

```python
"""
P2S Verifier & Deduplicator: Filters False Positives and deduplicates 5xx exception signatures.
Ensures ground-truth precision for paper reporting and artifact releases.
"""
from __future__ import annotations
import json, os, re, sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def extract_error_msg(res_body: Any) -> str:
    if isinstance(res_body, dict):
        msg = res_body.get("message") or res_body.get("error") or ""
        return str(msg).strip()
    elif isinstance(res_body, str):
        m = re.search(r'([a-zA-Z0-9_.]*(?:Exception|Error)[^\n\r"]*)', res_body)
        if m: return m.group(1).strip()
        return res_body[:90].strip()
    return "Unknown 5xx Error"


def inspect_and_validate_record(record: dict[str, Any]) -> tuple[bool, str, str]:
    """
    Evaluates a single Golden record for ground-truth security validity.
    Returns: (is_true_positive, category_code, explanation)
    """
    mutated_cmd = record.get("mutated_command", "") or ""
    actual_status = record.get("actual_status", 500)
    golden_label = record.get("golden_label", "")
    reasoning = ""
    messages = record.get("messages", [])
    if messages and isinstance(messages, list):
        reasoning = messages[-1].get("content", "")
    else:
        reasoning = record.get("reasoning", "")

    # Rule 1: CLI Help-Bleed
    is_help = "--help" in mutated_cmd or " -h" in mutated_cmd or mutated_cmd.endswith(" -h")
    if is_help:
        return False, "FP_HELP_BLEED", f"CLI --help executed instead of HTTP request."

    # Rule 2: HTTP 500 Unhandled Server Crash
    if actual_status >= 500 or golden_label == "GOLDEN_CRASH":
        return True, "TP_CRASH_500", "Unhandled 500 Internal Server Error."

    # Rule 3: HTTP 200/201 Security Bypasses
    if actual_status in [200, 201]:
        injected_mass_flags = [
            "iseditable", "candelete", "systemcriteria",
            "isadmin", "issuperuser", "skipapproval"
        ]
        has_mass_flag = any(f"--{f}" in mutated_cmd.lower() for f in injected_mass_flags)

        if has_mass_flag:
            record_str = json.dumps(record).lower()
            bound_property = any(
                f'"{f}":' in record_str or f'"{f}": true' in record_str
                for f in injected_mass_flags
            )
            if not bound_property:
                return False, "FP_JACKSON_IGNORED_PARAM", \
                       "Mass assignment flags silently ignored by Jackson."
            else:
                return True, "TP_MASS_ASSIGNMENT", \
                       "Injected read-only property successfully bound to database entity."

        has_token_override = "--api-bearer-token" in mutated_cmd
        has_id_swap = bool(re.search(
            r'--(?:id|userId|teamId|submissionId|roundId)\s+[\w-]{36}', mutated_cmd
        ))
        is_sec_reasoning = bool(re.search(
            r'\b(?:bola|bfla|idor)\b|bypass\s+(?:auth|role|permission|access)|privilege\s+escalat',
            reasoning, re.I
        ))

        if is_sec_reasoning and not (has_token_override or has_id_swap):
            return False, "FP_LEGITIMATE_AUTHORIZED_200", \
                   "Authorized 200 OK; no ID/JWT mutated."

        if has_token_override or has_id_swap or is_sec_reasoning:
            return True, "TP_BOLA_IDOR_BYPASS", \
                   "Confirmed BOLA/IDOR/Token manipulation → HTTP 200 OK."

        return True, "TP_SECURITY_BYPASS", "Confirmed 200 OK Security Bypass."

    return False, "FP_UNCLASSIFIED", f"Unclassified response with status {actual_status}."


def verify_golden_file(input_file: str, output_verified: str) -> dict[str, Any]:
    if not os.path.exists(input_file):
        print(f"[ERROR] Golden file not found: {input_file}"); return {}

    records = []
    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try: records.append(json.loads(line))
                except json.JSONDecodeError: pass

    true_positives, false_positives, categories = [], [], {}

    for rec in records:
        is_tp, cat_code, explanation = inspect_and_validate_record(rec)
        categories[cat_code] = categories.get(cat_code, 0) + 1
        if is_tp:
            rec["verified_category"] = cat_code; true_positives.append(rec)
        else:
            rec["fp_reason"] = cat_code; false_positives.append(rec)

    with open(output_verified, "w", encoding="utf-8") as f:
        for tp in true_positives:
            f.write(json.dumps(tp, ensure_ascii=False) + "\n")

    tp_cnt = len(true_positives); fp_cnt = len(false_positives)
    total_cnt = len(records)
    tp_pct = (tp_cnt / total_cnt * 100) if total_cnt > 0 else 0.0

    print("=" * 70)
    print("  P2S GOLDEN RECORD VERIFICATION REPORT")
    print(f"  Input File               : {input_file}")
    print(f"  Total Goldens Evaluated  : {total_cnt}")
    print(f"  True Positives (Verified): {tp_cnt} ({tp_pct:.1f}%)")
    print(f"  False Positives (Filtered): {fp_cnt} ({100 - tp_pct:.1f}%)")
    print("=" * 70)
    for cat, count in sorted(categories.items()):
        tag = "TP" if cat.startswith("TP") else "FP"
        print(f"    • [{tag}] {cat:<28} : {count}")
    print("=" * 70)
    print(f"  Saved Verified Goldens to : {output_verified}\n")

    return {
        "total": total_cnt, "true_positives": tp_cnt, "false_positives": fp_cnt,
        "tp_pct": tp_pct, "categories": categories
    }


def deduplicate_goldens(file_path: str, output_dedup: str = None) -> tuple[int, int]:
    if not os.path.exists(file_path):
        print(f"[ERROR] File not found: {file_path}"); return 0, 0

    unique_faults = {}; raw_count = 0; unique_records = []

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            raw_count += 1
            rec = json.loads(line)
            endpoint = rec.get("endpoint", "unknown")
            actual_status = rec.get("actual_status", 500)
            messages = rec.get("messages", [])
            res_body = messages[-1].get("content", "") \
                       if messages and isinstance(messages, list) \
                       else rec.get("response", {}).get("body", "")
            err_msg = extract_error_msg(res_body)
            fault_key = (endpoint, actual_status, err_msg)

            if fault_key not in unique_faults:
                unique_faults[fault_key] = {
                    "count": 1, "endpoint": endpoint,
                    "status": actual_status, "error_msg": err_msg
                }
                unique_records.append(rec)
            else:
                unique_faults[fault_key]["count"] += 1

    if output_dedup:
        with open(output_dedup, "w", encoding="utf-8") as f:
            for rec in unique_records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print("=" * 75)
    print("  P2S UNIQUE FAULT DEDUPLICATION REPORT")
    print(f"  Input File           : {file_path}")
    print(f"  Raw Golden Exploits  : {raw_count}")
    print(f"  UNIQUE FAULTS        : {len(unique_faults)}")
    print("=" * 75)
    for idx, (key, info) in enumerate(unique_faults.items(), 1):
        print(f"  [{idx:>2}] HTTP {info['status']} | Endpoint: {info['endpoint']}")
        print(f"       Exception Signature : {info['error_msg'][:80]}")
        print(f"       Triggered           : {info['count']} times\n")
    print("=" * 75 + "\n")

    return len(unique_faults), raw_count
```

**False-positive category codes:**

| Code | Meaning |
|---|---|
| `FP_HELP_BLEED` | Model emitted `--help` flag instead of a real request |
| `FP_JACKSON_IGNORED_PARAM` | Mass-assignment flag silently ignored by Spring Boot Jackson |
| `FP_LEGITIMATE_AUTHORIZED_200` | Authorized 200 OK with no resource ID or JWT mutation |
| `FP_UNCLASSIFIED` | Unexpected non-500 / non-200 status that was incorrectly promoted |
| `TP_CRASH_500` | Genuine unhandled 500 server crash |
| `TP_MASS_ASSIGNMENT` | Read-only property bound to entity (confirmed reflected) |
| `TP_BOLA_IDOR_BYPASS` | Confirmed BOLA/IDOR/token manipulation → 200 OK |
| `TP_SECURITY_BYPASS` | Other confirmed 200 OK security bypass |

---

## 12. Unified CLI Runner — `p2s_runner.py`

The master entry point. Wires all adapters together based on config and CLI mode. Supports 9 modes.

```python
#!/usr/bin/env python3
"""
P2S Master CLI Runner: 9-mode unified entry point.
Modes: proxy | compile | fuzz | generate-data | prepare-dataset |
       analyze | reclassify | m1 | verify
"""
import argparse
import sys
import json
import os
import importlib.util
from pathlib import Path

from p2s.config import load_config
from p2s.proxy.core_proxy import (
    P2SProxyServer, P2SProxyHandler, HeaderFlowStrategy, EndpointResetStrategy
)
from p2s.compiler.compiler import P2SCompiler
from p2s.engine.fuzzer import P2SFuzzer
from p2s.engine.generator import P2SDataGenerator
from p2s.engine.taxonomy import build_system_prompt
from p2s.engine.adapters.state_adapter import (
    PostgresTemplateAdapter, DockerRestartAdapter, StatelessAdapter
)
from p2s.engine.adapters.executor import OcliExecutorAdapter, RawHttpExecutorAdapter
from p2s.engine.adapters.llm_adapter import OpenAICompatAdapter, TransformersAdapter


def load_hook(script_path: str):
    """Dynamically loads a pre-snapshot Python hook from disk."""
    if not script_path or not os.path.exists(script_path): return None
    spec = importlib.util.spec_from_file_location("user_hook", script_path)
    hook_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook_module)
    return getattr(hook_module, "pre_snapshot_hook", None)


def hot_patch_openapi_spec(spec_path: str):
    """
    Relaxes 'required' validation constraints in the local OpenAPI spec copy so OCLI
    passes Vector 7 (Mandatory Omission) payloads to the backend rather than blocking
    them at the CLI layer.
    """
    if not os.path.exists(spec_path): return
    print(f"[*] Auto-patching OpenAPI spec ({spec_path}) to relax 'required' for Vector 7...")

    def recursive_delete_required(data):
        if isinstance(data, dict):
            if "required" in data and isinstance(data["required"], list):
                del data["required"]
            for v in list(data.values()): recursive_delete_required(v)
        elif isinstance(data, list):
            for item in data: recursive_delete_required(item)

    try:
        with open(spec_path, "r", encoding="utf-8") as f: spec = json.load(f)
        for pi in spec.get("paths", {}).values():
            for p in pi.get("parameters", []):
                if p.get("in") != "path" and p.get("required") is True:
                    p["required"] = False
            for m in ["get", "post", "put", "delete", "patch"]:
                if m in pi:
                    for p in pi[m].get("parameters", []):
                        if p.get("in") != "path" and p.get("required") is True:
                            p["required"] = False
        recursive_delete_required(spec)
        with open(spec_path, "w", encoding="utf-8") as f:
            json.dump(spec, f, ensure_ascii=False, indent=2)
        print("[+] Auto-patching complete.")
    except Exception as e:
        print(f"[WARN] Failed to patch spec: {e}")


def _build_state_adapter(config):
    if config.target.state_adapter == "postgres":
        user_hook = load_hook(config.postgres.setup_script) \
                    if hasattr(config.postgres, "setup_script") else None
        return PostgresTemplateAdapter(
            config.postgres.active_db, config.postgres.template_db, config.postgres.admin_url,
            seed_command=getattr(config.postgres, "seed_command", None),
            pre_snapshot_hook=user_hook
        )
    elif config.target.state_adapter == "docker":
        return DockerRestartAdapter(config.target.name)
    else:
        return StatelessAdapter()


def _build_executor(config):
    if config.target.executor_adapter == "ocli":
        return OcliExecutorAdapter(
            profile_name=config.target.name, target_url=config.target.base_url
        )
    else:
        return RawHttpExecutorAdapter(
            base_url=config.target.base_url, spec_path=config.target.openapi_spec
        )


def _build_llm(config):
    if config.llm.backend == "openai_compat":
        return OpenAICompatAdapter(config.llm.base_url, config.llm.api_key, config.llm.model)
    else:
        return TransformersAdapter(config.llm.model)


def _load_catalog_str():
    if os.path.exists("ocli_catalog.json"):
        with open("ocli_catalog.json") as f: return f.read()
    return ""


def main():
    print("""
    ██████╗  ██████╗ ███████╗
    ██╔══██╗   ██╔═╝ ██╔════╝
    ██████╔╝ █████╗  ███████╗
    ██╔═══╝ ██╔═══╝  ╚════██║
    ██║     ███████╗ ███████║
    ╚═╝     ╚══════╝ ╚══════╝ API Security Framework
    """)

    parser = argparse.ArgumentParser(
        description="P2S Framework: Execution-Verified Fuzzer, Data Generator & Analytics Engine"
    )
    parser.add_argument(
        "mode",
        choices=[
            "proxy", "compile", "fuzz",
            "generate-data", "prepare-dataset",
            "analyze", "reclassify", "m1", "verify"
        ],
        help="Mode of operation"
    )
    parser.add_argument("-c", "--config", help="Path to config TOML")
    parser.add_argument(
        "--dir", default=".", help="Directory for auto-discovering datasets (analyze mode)"
    )
    parser.add_argument(
        "--backend", default="llamacpp",
        help="Backend prefix for reclassify/m1 modes (e.g. llamacpp, openai)"
    )
    parser.add_argument(
        "--slm-url", default="http://localhost:1234/v1",
        help="SLM URL for offline reclassification"
    )
    parser.add_argument(
        "--golden-file", default="llamacpp_golden_dataset_reclassified.jsonl",
        help="Input golden file for verify mode"
    )
    parser.add_argument(
        "--verified-out", default="seal_p2s_verified_goldens.jsonl",
        help="Output verified file for verify mode"
    )
    args = parser.parse_args()

    if args.mode in ("proxy", "compile", "fuzz", "generate-data") and not args.config:
        parser.error(f"--config is required for mode '{args.mode}'")

    # ── PROXY ──────────────────────────────────────────────────────────────────
    if args.mode == "proxy":
        config = load_config(args.config)
        strategy = (
            HeaderFlowStrategy() if config.proxy.flow_strategy == "header"
            else EndpointResetStrategy(config.proxy.reset_endpoint)
        )
        server = P2SProxyServer(
            ("0.0.0.0", config.proxy.listen_port), P2SProxyHandler,
            config.proxy.target_host, strategy, config.proxy.output_file
        )
        print(f"[*] Proxy running on :{config.proxy.listen_port} -> {config.proxy.target_host}")
        try: server.serve_forever()
        except KeyboardInterrupt: print("\n[PROXY] Shutting down.")

    # ── COMPILE ────────────────────────────────────────────────────────────────
    elif args.mode == "compile":
        config = load_config(args.config)
        compiler = P2SCompiler(swagger_path=config.target.openapi_spec)
        compiler.compile(
            input_file=config.proxy.output_file,
            output_file="compiled_traces.jsonl",
            catalog_file="ocli_catalog.json"
        )

    # ── FUZZ (Eval) ────────────────────────────────────────────────────────────
    elif args.mode == "fuzz":
        config = load_config(args.config)
        hot_patch_openapi_spec(config.target.openapi_spec)
        state = _build_state_adapter(config)
        executor = _build_executor(config)
        llm = _build_llm(config)
        sys_prompt = build_system_prompt(config.target.executor_adapter,
                                         ocli_catalog=_load_catalog_str())
        fuzzer = P2SFuzzer(
            state, executor, llm, sys_prompt,
            config.target.golden_out, config.target.silver_out, config.target.checkpoint_file
        )
        fuzzer.run_all(traces_file="compiled_traces.jsonl", max_attempts=config.llm.max_attempts)

    # ── GENERATE-DATA (Train) ──────────────────────────────────────────────────
    elif args.mode == "generate-data":
        config = load_config(args.config)
        state = _build_state_adapter(config)
        executor = _build_executor(config)
        llm = _build_llm(config)
        sys_prompt = build_system_prompt("ocli", ocli_catalog=_load_catalog_str())
        generator = P2SDataGenerator(
            state, executor, llm, sys_prompt,
            config.target.golden_out, config.target.silver_out, config.target.checkpoint_file
        )
        generator.generate_corpus(
            traces_file="compiled_traces.jsonl", max_attempts=config.llm.max_attempts
        )

    # ── PREPARE-DATASET ────────────────────────────────────────────────────────
    elif args.mode == "prepare-dataset":
        config = load_config(args.config) if args.config else None
        golden_file = config.target.golden_out if config else "golden_dataset.jsonl"
        silver_file = config.target.silver_out if config else "silver_dataset.jsonl"
        from p2s.dataset.builder import prepare_stratified_dataset
        prepare_stratified_dataset(
            golden_file=golden_file, silver_file=silver_file,
            output_file="final_training_dataset.jsonl",
            max_seq_length=24576, seed=3407
        )

    # ── ANALYZE ────────────────────────────────────────────────────────────────
    elif args.mode == "analyze":
        from p2s.analytics.analyzer import RunPair, analyze_run, print_report
        search_dir = Path(args.dir)
        pairs = []
        for gf in sorted(search_dir.glob(f"*{GOLDEN_SUFFIX}")):
            label = gf.name.replace(GOLDEN_SUFFIX, "")
            sf = search_dir / f"{label}{SILVER_SUFFIX}"
            mf = search_dir / f"{label}{METADATA_SUFFIX}"
            if sf.exists():
                pairs.append(RunPair(label=label, golden_path=gf, silver_path=sf, metadata_path=mf))
        if not pairs:
            print("[WARN] No matching dataset triplets found in directory.")
        else:
            runs = [analyze_run(p) for p in pairs]
            print_report(runs)

    # ── RECLASSIFY ────────────────────────────────────────────────────────────
    elif args.mode == "reclassify":
        from p2s.analytics.reclassifier import process_file
        golden = f"{args.backend}_golden_dataset.jsonl"
        silver = f"{args.backend}_silver_dataset.jsonl"
        process_file(golden, f"{args.backend}_golden_dataset_reclassified.jsonl", args.slm_url)
        process_file(silver, f"{args.backend}_silver_dataset_reclassified.jsonl", args.slm_url)

    # ── M1 ─────────────────────────────────────────────────────────────────────
    elif args.mode == "m1":
        from p2s.analytics.m1_analyzer import run_m1_analysis
        run_m1_analysis(backend_prefix=args.backend)

    # ── VERIFY ─────────────────────────────────────────────────────────────────
    elif args.mode == "verify":
        from p2s.analytics.verifier import verify_golden_file, deduplicate_goldens
        verify_golden_file(args.golden_file, args.verified_out)
        deduplicate_goldens(args.verified_out)


GOLDEN_SUFFIX = "_golden_dataset.jsonl"
SILVER_SUFFIX = "_silver_dataset.jsonl"
METADATA_SUFFIX = "_run_metadata.json"


if __name__ == "__main__":
    main()
```

### Mode Reference

| Mode | Required Flags | Output |
|---|---|---|
| `proxy` | `--config` | `primitive_traces.jsonl` |
| `compile` | `--config` | `compiled_traces.jsonl`, `ocli_catalog.json` |
| `fuzz` | `--config` | `*_golden_dataset.jsonl`, `*_silver_dataset.jsonl`, `p2s_run_metadata.json` |
| `generate-data` | `--config` | Same as fuzz, with richer annotation |
| `prepare-dataset` | `--config` (optional) | `final_training_dataset.jsonl` |
| `analyze` | `--dir` | Console report |
| `reclassify` | `--backend`, `--slm-url` | `*_reclassified.jsonl` |
| `m1` | `--backend` | Console report, updates `*_run_metadata.json` |
| `verify` | `--golden-file`, `--verified-out` | Verified JSONL + dedup report |

---

## 13. Example Configurations & Hooks

### `configs/seal_hackathon.toml` (Spring Boot + PostgreSQL + OCLI)

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

### `configs/aitasker.toml` (NestJS / Prisma + PostgreSQL + OCLI)

```toml
[target]
name = "aitasker"
base_url = "http://localhost:3000/api"
openapi_spec = "aitasker_openapi.json"
state_adapter = "postgres"
executor_adapter = "ocli"
golden_out = "aitasker_golden_dataset.jsonl"
silver_out = "aitasker_silver_dataset.jsonl"
checkpoint_file = "aitasker_processed_flows.txt"

[postgres]
active_db = "aitasker_active"
template_db = "aitasker_snap"
admin_url = "postgresql://postgres:postgres@localhost:5434/postgres"
seed_command = "npx prisma db push --accept-data-loss && npx prisma db execute --file=prisma/migrations/010_seed.sql"

[llm]
backend = "openai_compat"
base_url = "http://localhost:8081/v1"
model = "qwen35-9b-p2s"
api_key = "no-key"
max_attempts = 6

[proxy]
listen_port = 8091
target_host = "http://localhost:3000"
flow_strategy = "endpoint"
reset_endpoint = "/auth/register"
output_file = "aitasker_primitive_traces.jsonl"
```

### Seed Command Examples by Stack

| Stack | `seed_command` |
|---|---|
| Spring Boot / Raw SQL | `psql -U postgres -d mydb -f schema_seed.sql` |
| NestJS / Prisma | `npx prisma db push --accept-data-loss && npx prisma db execute --file=seed.sql` |
| Django | `python manage.py migrate && python manage.py loaddata seed_data.json` |
| Omitted | *(P2S assumes `active_db` is pre-seeded)* |

### `hooks/seal_setup_hook.py` (Pre-Snapshot Hook)

Hooks run once after the seed command and before the first snapshot freeze. They can make HTTP calls to register test accounts or run raw SQL to sync UUIDs from traces.

```python
import requests, time, psycopg2

def pre_snapshot_hook(active_db_name: str):
    """
    Registers the Coordinator account and forces DB roles to match trace UUIDs
    before P2S freezes the first Postgres template snapshot.
    """
    print(f"[*] SEAL Hook: Registering Coordinator on '{active_db_name}'...")
    try:
        requests.post("http://localhost:8080/api/auth/register", json={
            "email": "coordinator@seal.eval",
            "password": "Eval@1234567",
            "fullName": "P2S Eval Coordinator"
        }, timeout=10)
        time.sleep(1)

        # Exact UUID from the captured traces
        coord_id = "f6aedc49-ab54-4ed2-9668-abc9eb337e34"

        conn = psycopg2.connect(
            f"postgresql://postgres:postgres@localhost:5432/{active_db_name}"
        )
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM user_roles "
                "WHERE user_id=(SELECT id FROM users WHERE email='coordinator@seal.eval');"
            )
            cur.execute(
                f"UPDATE users SET id='{coord_id}', status='approved' "
                f"WHERE email='coordinator@seal.eval';"
            )
            cur.execute(
                f"INSERT INTO user_roles (user_id, role_id) "
                f"SELECT '{coord_id}', id FROM roles "
                f"WHERE name IN ('team_member', 'coordinator') ON CONFLICT DO NOTHING;"
            )
        conn.close()
        print("[+] SEAL Hook complete.")
    except Exception as e:
        print(f"[!] SEAL Hook failed: {e}")
```

The hook contract is universal: create a `.py` file with a single `pre_snapshot_hook(active_db_name: str)` function, point `setup_script` to it in TOML, and P2S handles the rest.

---

## 14. Workflow Guides

### Evaluation Workflow (Fuzzing / Security Reporting)

```bash
# 1. Start the target backend, then start the transparent proxy
p2s proxy --config configs/seal_hackathon.toml

# 2. Run your test suite with the proxy as the HTTP target
#    (The proxy logs every request/response to primitive_traces.jsonl)

# 3. Compile raw traces into OCLI commands + catalog
p2s compile --config configs/seal_hackathon.toml

# 4. Launch the execution-verified fuzzer
p2s fuzz --config configs/seal_hackathon.toml
#    → llamacpp_golden_dataset.jsonl (crashes + RBAC bypasses)
#    → llamacpp_silver_dataset.jsonl (defensive boundaries)
#    → p2s_run_metadata.json

# 5. Post-hoc analytics
p2s analyze --dir .

p2s reclassify --backend llamacpp --slm-url http://localhost:1234/v1

p2s m1 --backend llamacpp

p2s verify \
    --golden-file llamacpp_golden_dataset_reclassified.jsonl \
    --verified-out seal_p2s_verified_goldens.jsonl
```

### Training Data Generation Workflow

```bash
# Steps 1-3 are identical to the Eval Workflow above.

# 4. Run Teacher-Critic self-play data generation
p2s generate-data --config configs/seal_hackathon.toml
#    → golden_dataset.jsonl (enriched think-block annotations)
#    → silver_dataset.jsonl

# 5. Build stratified training corpus
p2s prepare-dataset --config configs/seal_hackathon.toml
#    → final_training_dataset.jsonl (deduplicated, oversampled, token-scanned)

# 6. Upload final_training_dataset.jsonl to Colab A100 and run p2s_colab_train.py
```

### Plugging in a New Target

1. Copy an existing TOML from `configs/` and update `[target]`, `[postgres]`, `[proxy]`.
2. If the backend needs pre-snapshot setup (account registration, UUID alignment), create `hooks/<target>_setup.py` with `def pre_snapshot_hook(active_db_name): ...`.
3. Point `setup_script` in the TOML to the new hook file.
4. Run `p2s proxy`, `p2s compile`, then either `p2s fuzz` or `p2s generate-data`.

No framework code needs to change between targets — only the TOML and the optional hook file.

---

*End of P2S Framework Unified Technical Reference.*
*The Colab A100 SFT training notebook is distributed separately as `p2s_colab_train.py`.*
