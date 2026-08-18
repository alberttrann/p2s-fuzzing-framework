"""P2S configuration parser.

v1.2 moves research-reproduction differences into declarative TOML: target
patches, target launch/record/coverage commands, OpenAPI acquisition and
sanitisation, controlled test authentication, OCLI credentials, heterogeneous
state reset commands, and hard wall-clock budgets all use the same SDK code.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any

try:
    import tomllib
except ImportError:  # pragma: no cover - Python < 3.11
    import tomli as tomllib


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
    context_path_prefix: str = ""


@dataclass
class PostgresConfig:
    active_db: str = ""
    template_db: str = ""
    admin_url: str = ""
    seed_command: str = ""
    setup_script: str = ""  # backwards-compatible pre-snapshot Python hook
    recreate_active_before_seed: bool = False
    post_seed_commands: list[str] = field(default_factory=list)


@dataclass
class DockerConfig:
    container_name: str = ""
    restart_sleep_seconds: float = 2.0


@dataclass
class MongoConfig:
    db_name: str = ""
    mongo_uri: str = ""
    dump_dir: str = "/tmp/p2s_mongo_snap"


@dataclass
class FileStateConfig:
    active_path: str = ""
    backup_path: str = ""


@dataclass
class CommandStateConfig:
    """Generic snapshot/reset commands for heterogeneous benchmark targets."""

    create_snapshot_command: str = ""
    create_snapshot_command_env: str = ""
    restore_snapshot_command: str = ""
    restore_snapshot_command_env: str = ""
    working_directory: str = ""
    restore_sleep_seconds: float = 0.0


@dataclass
class LLMConfig:
    backend: str = "openai_compat"
    base_url: str = "http://localhost:8081/v1"
    model: str = "qwen35-9b"
    api_key: str = "no-key"
    api_key_env: str = ""
    max_attempts: int = 6


@dataclass
class OcliConfig:
    profile_name: str = ""
    api_base_url: str = ""
    openapi_spec: str = ""
    bearer_token: str = ""
    bearer_token_env: str = ""
    bearer_token_file: str = ""
    basic_auth: str = ""
    basic_auth_env: str = ""
    basic_auth_file: str = ""
    command_prefix: str = ""
    throttle_delay_seconds: float = 0.015
    timeout_seconds: int = 150


@dataclass
class ProxyConfig:
    listen_port: int = 8090
    target_host: str = "http://localhost:8080"
    flow_strategy: str = "header"
    reset_endpoint: str = "/auth/register"
    output_file: str = "primitive_traces.jsonl"
    mask_sensitive_headers: bool = True


@dataclass
class PatchConfig:
    """One idempotent research-environment file patch.

    Supported kinds: ``replace``, ``regex_replace``, ``write``, and ``append``.
    """

    kind: str = "replace"
    path: str = ""
    find: str = ""
    replace: str = ""
    content: str = ""
    required: bool = True
    count: int = 0


@dataclass
class OpenAPISetupConfig:
    """Native OpenAPI acquisition/sanitisation used by reproduction configs."""

    source_url: str = ""
    output_file: str = ""
    server_url: str = ""
    remove_paths: list[str] = field(default_factory=list)
    # Entries use the readable form ``METHOD /path/{id}``.
    remove_operations: list[str] = field(default_factory=list)


@dataclass
class AuthConfig:
    """Controlled test credential acquisition.

    ``mode='bearer_login'`` sends ``login_body`` as JSON and stores the field
    selected by ``token_json_field`` in ``token_output_file``.  This replaces
    target-specific token-fetch helper scripts while keeping credentials out of
    primitive traces when the proxy masks sensitive headers.
    """

    mode: str = ""
    login_url: str = ""
    login_body: dict[str, Any] = field(default_factory=dict)
    token_json_field: str = "accessToken"
    token_output_file: str = ".p2s/bearer_token.txt"
    pre_login_commands: list[str] = field(default_factory=list)


@dataclass
class ResearchConfig:
    """Framework-native lifecycle settings for research reproduction."""

    root_dir: str = "."
    prepare_commands: list[str] = field(default_factory=list)
    record_command: str = ""
    # Optional trace file produced by the configured workload itself.  When set,
    # ``p2s record`` freezes this file instead of the framework proxy output.
    # This is useful for RESTgym, whose workload fixtures already emit the P2S
    # primitive-trace schema while requests must continue traversing RESTgym's
    # semantically-active mitmproxy on host port 9090.
    record_trace_source: str = ""
    record_snapshot_file: str = "baseline_primitive_traces.jsonl"
    coverage_command: str = ""
    cleanup_commands: list[str] = field(default_factory=list)
    readiness_url: str = ""
    readiness_timeout_seconds: int = 60
    readiness_interval_seconds: float = 1.0
    time_budget_seconds: int = 0
    cyclic: bool = False
    patch_openapi_required: bool = True
    clear_checkpoint_for_cyclic: bool = True
    reset_before_each_target: bool = False
    reset_before_each_flow: bool = False
    pre_step_replay: str = "last"  # last | all | none
    require_attack_flag_for_2xx: bool = False
    runtime_openapi_file: str = "p2s_runtime_openapi.json"


@dataclass
class P2SConfig:
    target: TargetConfig
    llm: LLMConfig
    proxy: ProxyConfig
    postgres: PostgresConfig = field(default_factory=PostgresConfig)
    docker: DockerConfig = field(default_factory=DockerConfig)
    mongo: MongoConfig = field(default_factory=MongoConfig)
    file_state: FileStateConfig = field(default_factory=FileStateConfig)
    command_state: CommandStateConfig = field(default_factory=CommandStateConfig)
    ocli: OcliConfig = field(default_factory=OcliConfig)
    openapi_setup: OpenAPISetupConfig = field(default_factory=OpenAPISetupConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    research: ResearchConfig = field(default_factory=ResearchConfig)
    patches: list[PatchConfig] = field(default_factory=list)


def _coerce_patches(raw: Any) -> list[PatchConfig]:
    if not raw:
        return []
    if not isinstance(raw, list):
        raise TypeError("[[patches]] must be an array of TOML tables")
    return [PatchConfig(**item) for item in raw]


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
    docker = DockerConfig(**data.get("docker", {}))
    mongo = MongoConfig(**data.get("mongo", {}))
    file_state = FileStateConfig(**data.get("file_state", {}))
    command_state = CommandStateConfig(**data.get("command_state", {}))
    ocli = OcliConfig(**data.get("ocli", {}))
    openapi_setup = OpenAPISetupConfig(**data.get("openapi_setup", {}))
    auth = AuthConfig(**data.get("auth", {}))
    research = ResearchConfig(**data.get("research", {}))
    patches = _coerce_patches(data.get("patches", []))

    return P2SConfig(
        target=target,
        llm=llm,
        proxy=proxy,
        postgres=postgres,
        docker=docker,
        mongo=mongo,
        file_state=file_state,
        command_state=command_state,
        ocli=ocli,
        openapi_setup=openapi_setup,
        auth=auth,
        research=research,
        patches=patches,
    )
