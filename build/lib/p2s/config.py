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
