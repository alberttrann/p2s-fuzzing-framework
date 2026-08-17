"""P2S — Execution-Verified API Security Testing & Dataset Generation SDK."""
from .config import LLMConfig, P2SConfig, PostgresConfig, ProxyConfig, TargetConfig, load_config
from .sdk import P2S, P2SClient, P2SConfigurationError, P2SError, patch_openapi_required

__version__ = "1.1.0"

__all__ = [
    "P2S",
    "P2SClient",
    "P2SConfig",
    "TargetConfig",
    "LLMConfig",
    "ProxyConfig",
    "PostgresConfig",
    "load_config",
    "P2SError",
    "P2SConfigurationError",
    "patch_openapi_required",
    "__version__",
]
