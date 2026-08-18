"""P2S — Execution-Verified API Security Testing & Dataset Generation SDK."""
from .config import (
    AuthConfig, CommandStateConfig, DockerConfig, FileStateConfig, LLMConfig, MongoConfig,
    OcliConfig, OpenAPISetupConfig, P2SConfig, PatchConfig, PostgresConfig, ProxyConfig,
    ResearchConfig, TargetConfig, load_config,
)
from .sdk import P2S, P2SClient, P2SConfigurationError, P2SError, patch_openapi_required

__version__ = "1.2.0"

__all__ = [
    "P2S", "P2SClient", "P2SConfig", "TargetConfig", "LLMConfig",
    "ProxyConfig", "PostgresConfig", "DockerConfig", "MongoConfig",
    "FileStateConfig", "CommandStateConfig", "OcliConfig", "OpenAPISetupConfig",
    "AuthConfig", "ResearchConfig", "PatchConfig", "load_config", "P2SError",
    "P2SConfigurationError",
    "patch_openapi_required", "__version__",
]
