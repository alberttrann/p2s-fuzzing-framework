"""High-level Python SDK for the P2S framework.

The SDK is a programmatic facade over the same compiler, proxy, fuzzing,
generation, dataset, and analytics components used by the CLI.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from .config import P2SConfig, load_config
from .compiler.compiler import P2SCompiler
from .dataset.builder import prepare_stratified_dataset
from .engine.fuzzer import P2SFuzzer
from .engine.generator import P2SDataGenerator
from .engine.taxonomy import build_system_prompt
from .engine.adapters.executor import OcliExecutorAdapter, RawHttpExecutorAdapter
from .engine.adapters.llm_adapter import OpenAICompatAdapter, TransformersAdapter
from .engine.adapters.state_adapter import (
    DockerRestartAdapter,
    FileBackupAdapter,
    MongoDumpAdapter,
    PostgresTemplateAdapter,
    StatelessAdapter,
)
if TYPE_CHECKING:
    from .proxy.core_proxy import P2SProxyServer


class P2SError(RuntimeError):
    """Base SDK exception."""


class P2SConfigurationError(P2SError):
    """Raised when an SDK operation cannot be built from the active configuration."""


def _load_hook(script_path: str):
    if not script_path:
        return None
    path = Path(script_path)
    if not path.exists():
        raise P2SConfigurationError(f"Configured setup hook does not exist: {path}")
    spec = importlib.util.spec_from_file_location("p2s_user_hook", path)
    if spec is None or spec.loader is None:
        raise P2SConfigurationError(f"Could not load setup hook: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, "pre_snapshot_hook", None)


def patch_openapi_required(spec_path: str | os.PathLike[str]) -> Path:
    """Relax non-path OpenAPI ``required`` constraints for omission testing.

    This preserves path-parameter requirements while removing schema-level and
    non-path required lists so Vector 7 requests can reach the target backend.
    The file is modified in-place and the resolved path is returned.
    """
    path = Path(spec_path)
    if not path.exists():
        raise FileNotFoundError(path)

    def delete_required(node):
        if isinstance(node, dict):
            if isinstance(node.get("required"), list):
                node.pop("required", None)
            for value in node.values():
                delete_required(value)
        elif isinstance(node, list):
            for item in node:
                delete_required(item)

    with path.open("r", encoding="utf-8") as handle:
        spec = json.load(handle)

    for path_item in spec.get("paths", {}).values():
        if not isinstance(path_item, dict):
            continue
        for parameter in path_item.get("parameters", []):
            if parameter.get("in") != "path" and parameter.get("required") is True:
                parameter["required"] = False
        for method in ("get", "post", "put", "patch", "delete"):
            operation = path_item.get(method)
            if not isinstance(operation, dict):
                continue
            for parameter in operation.get("parameters", []):
                if parameter.get("in") != "path" and parameter.get("required") is True:
                    parameter["required"] = False

    delete_required(spec)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(spec, handle, ensure_ascii=False, indent=2)
    return path.resolve()


class P2S:
    """Primary high-level P2S SDK facade.

    Parameters
    ----------
    config:
        Fully parsed :class:`~p2s.config.P2SConfig`.
    workdir:
        Directory where compiled traces, catalogs, datasets, and metadata are
        read/written. Defaults to the current working directory.
    """

    def __init__(self, config: P2SConfig, workdir: str | os.PathLike[str] = "."):
        self.config = config
        self.workdir = Path(workdir).expanduser().resolve()
        self.workdir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_toml(
        cls,
        config_path: str | os.PathLike[str],
        *,
        workdir: str | os.PathLike[str] = ".",
    ) -> "P2S":
        """Create an SDK instance from a P2S TOML configuration file."""
        return cls(load_config(str(config_path)), workdir=workdir)

    def _workpath(self, name: str | os.PathLike[str]) -> Path:
        path = Path(name)
        return path if path.is_absolute() else self.workdir / path

    def _catalog_text(self, catalog_file: str = "ocli_catalog.json") -> str:
        path = self._workpath(catalog_file)
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def build_state_adapter(self):
        """Instantiate the state adapter selected by the active configuration."""
        kind = self.config.target.state_adapter.lower()
        if kind == "postgres":
            hook = _load_hook(self.config.postgres.setup_script)
            return PostgresTemplateAdapter(
                self.config.postgres.active_db,
                self.config.postgres.template_db,
                self.config.postgres.admin_url,
                seed_command=self.config.postgres.seed_command or None,
                pre_snapshot_hook=hook,
            )
        if kind == "docker":
            return DockerRestartAdapter(self.config.target.name)
        if kind == "stateless":
            return StatelessAdapter()
        if kind == "mongo":
            raise P2SConfigurationError(
                "Mongo state requires explicit db_name/mongo_uri; construct MongoDumpAdapter "
                "directly or extend your application configuration."
            )
        if kind == "file":
            raise P2SConfigurationError(
                "File state requires active/backup paths; construct FileBackupAdapter directly "
                "or extend your application configuration."
            )
        raise P2SConfigurationError(f"Unknown state_adapter: {kind}")

    def build_executor(self):
        """Instantiate the configured OCLI or raw-HTTP executor."""
        kind = self.config.target.executor_adapter.lower()
        if kind == "ocli":
            return OcliExecutorAdapter(
                profile_name=self.config.target.name,
                target_url=self.config.target.base_url,
                catalog_path=str(self._workpath("ocli_catalog.json")),
            )
        if kind in {"http", "raw_http", "raw-http"}:
            return RawHttpExecutorAdapter(
                base_url=self.config.target.base_url,
                spec_path=self.config.target.openapi_spec,
            )
        raise P2SConfigurationError(f"Unknown executor_adapter: {kind}")

    def build_llm(self):
        """Instantiate the configured LLM adapter."""
        kind = self.config.llm.backend.lower()
        if kind == "openai_compat":
            return OpenAICompatAdapter(
                self.config.llm.base_url,
                self.config.llm.api_key,
                self.config.llm.model,
            )
        if kind in {"transformers", "huggingface", "hf"}:
            return TransformersAdapter(self.config.llm.model)
        raise P2SConfigurationError(f"Unknown llm backend: {kind}")

    def create_proxy_server(self, *, host: str = "0.0.0.0") -> "P2SProxyServer":
        """Build, but do not start, the configured transparent proxy server."""
        from .proxy.core_proxy import (
            EndpointResetStrategy, HeaderFlowStrategy, P2SProxyHandler, P2SProxyServer
        )
        strategy = (
            HeaderFlowStrategy()
            if self.config.proxy.flow_strategy == "header"
            else EndpointResetStrategy(self.config.proxy.reset_endpoint)
        )
        return P2SProxyServer(
            (host, self.config.proxy.listen_port),
            P2SProxyHandler,
            self.config.proxy.target_host,
            strategy,
            str(self._workpath(self.config.proxy.output_file)),
        )

    def run_proxy(self, *, host: str = "0.0.0.0") -> None:
        """Run the configured proxy until interrupted."""
        server = self.create_proxy_server(host=host)
        try:
            server.serve_forever()
        finally:
            server.server_close()

    def compile(
        self,
        *,
        input_file: Optional[str] = None,
        output_file: str = "compiled_traces.jsonl",
        catalog_file: str = "ocli_catalog.json",
        context_path_prefix: str = "/api",
    ) -> tuple[Path, Path]:
        """Compile captured primitive traces into typed executable traces."""
        compiler = P2SCompiler(
            swagger_path=self.config.target.openapi_spec,
            context_path_prefix=context_path_prefix,
        )
        source = input_file or self.config.proxy.output_file
        out = self._workpath(output_file)
        catalog = self._workpath(catalog_file)
        compiler.compile(str(self._workpath(source)), str(out), str(catalog))
        return out, catalog

    def fuzz(
        self,
        *,
        traces_file: str = "compiled_traces.jsonl",
        max_attempts: Optional[int] = None,
        patch_openapi: bool = True,
    ) -> P2SFuzzer:
        """Run execution-verified evaluation fuzzing and return the populated engine."""
        if patch_openapi:
            patch_openapi_required(self.config.target.openapi_spec)
        engine = P2SFuzzer(
            self.build_state_adapter(),
            self.build_executor(),
            self.build_llm(),
            build_system_prompt(
                self.config.target.executor_adapter,
                ocli_catalog=self._catalog_text(),
            ),
            str(self._workpath(self.config.target.golden_out)),
            str(self._workpath(self.config.target.silver_out)),
            str(self._workpath(self.config.target.checkpoint_file)),
        )
        engine.run_all(
            traces_file=str(self._workpath(traces_file)),
            max_attempts=max_attempts or self.config.llm.max_attempts,
        )
        return engine

    def generate_data(
        self,
        *,
        traces_file: str = "compiled_traces.jsonl",
        max_attempts: Optional[int] = None,
    ) -> P2SDataGenerator:
        """Run Teacher-Critic self-play generation and return the generator engine."""
        engine = P2SDataGenerator(
            self.build_state_adapter(),
            self.build_executor(),
            self.build_llm(),
            build_system_prompt("ocli", ocli_catalog=self._catalog_text()),
            str(self._workpath(self.config.target.golden_out)),
            str(self._workpath(self.config.target.silver_out)),
            str(self._workpath(self.config.target.checkpoint_file)),
        )
        engine.generate_corpus(
            traces_file=str(self._workpath(traces_file)),
            max_attempts=max_attempts or self.config.llm.max_attempts,
        )
        return engine

    def prepare_dataset(
        self,
        *,
        golden_file: Optional[str] = None,
        silver_file: Optional[str] = None,
        output_file: str = "final_training_dataset.jsonl",
        max_seq_length: int = 24576,
        seed: int = 3407,
    ) -> Path:
        """Deduplicate and stratify P2S Golden/Silver records into an SFT corpus."""
        output = self._workpath(output_file)
        prepare_stratified_dataset(
            golden_file=str(self._workpath(golden_file or self.config.target.golden_out)),
            silver_file=str(self._workpath(silver_file or self.config.target.silver_out)),
            output_file=str(output),
            max_seq_length=max_seq_length,
            seed=seed,
        )
        return output


# More explicit alias for SDK-oriented naming.
P2SClient = P2S

__all__ = [
    "P2S",
    "P2SClient",
    "P2SError",
    "P2SConfigurationError",
    "patch_openapi_required",
]
