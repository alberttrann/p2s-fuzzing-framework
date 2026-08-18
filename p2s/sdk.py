"""High-level Python SDK for the P2S framework.

v1.2 makes the research-reproduction path framework-native: target-specific
patches, lifecycle commands, OCLI authentication, reset strategies, and hard
cyclic budgets live in TOML while proxy/compiler/fuzzer code stays shared.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
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
    CommandStateAdapter,
    DockerRestartAdapter,
    FileBackupAdapter,
    MongoDumpAdapter,
    PostgresTemplateAdapter,
    StatelessAdapter,
)
from .research.lifecycle import ResearchLifecycle

if TYPE_CHECKING:
    from .proxy.core_proxy import P2SProxyServer


class P2SError(RuntimeError):
    """Base SDK exception."""


class P2SConfigurationError(P2SError):
    """Raised when an SDK operation cannot be built from the active configuration."""


def _load_hook(script_path: Path | str):
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

    Path parameters remain required.  Schema-level ``required`` arrays and
    non-path parameter requirements are removed in-place, reproducing the
    evaluation-time omission-testing relaxation used in Track A.
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

    text = path.read_text(encoding="utf-8")
    try:
        spec = json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("YAML OpenAPI input requires PyYAML") from exc
        spec = yaml.safe_load(text)
        if not isinstance(spec, dict):
            raise ValueError(f"OpenAPI document is not an object: {path}")

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
    """Primary high-level P2S SDK facade."""

    def __init__(
        self,
        config: P2SConfig,
        workdir: str | os.PathLike[str] = ".",
        *,
        config_dir: str | os.PathLike[str] = ".",
    ):
        self.config = config
        self.workdir = Path(workdir).expanduser().resolve()
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.config_dir = Path(config_dir).expanduser().resolve()
        self.lifecycle = ResearchLifecycle(
            config,
            config_dir=self.config_dir,
            workdir=self.workdir,
        )

    @classmethod
    def from_toml(
        cls,
        config_path: str | os.PathLike[str],
        *,
        workdir: str | os.PathLike[str] = ".",
    ) -> "P2S":
        path = Path(config_path).expanduser().resolve()
        return cls(load_config(str(path)), workdir=workdir, config_dir=path.parent)

    def _workpath(self, name: str | os.PathLike[str]) -> Path:
        path = Path(name)
        return path if path.is_absolute() else self.workdir / path

    def _rootpath(self, name: str | os.PathLike[str]) -> Path:
        return self.lifecycle.resolve(name)

    def _spec_path(self) -> Path:
        return self._rootpath(self.config.target.openapi_spec)

    def _catalog_text(self, catalog_file: str = "ocli_catalog.json") -> str:
        path = self._workpath(catalog_file)
        return path.read_text(encoding="utf-8") if path.exists() else ""

    # ------------------------------------------------------------------
    # Research lifecycle
    # ------------------------------------------------------------------
    def prepare(self):
        """Apply configured research patches, launch commands, and readiness checks."""
        return self.lifecycle.prepare()

    def patch(self):
        """Apply only configured idempotent target patches."""
        return self.lifecycle.apply_patches()

    def fetch_openapi(self):
        """Fetch/sanitise OpenAPI using [openapi_setup]."""
        return self.lifecycle.fetch_openapi()

    def acquire_auth(self):
        """Acquire the configured controlled test credential."""
        return self.lifecycle.acquire_auth()

    def record(self) -> None:
        """Run the configured workload and freeze its baseline primitive trace.

        By default the source is the P2S proxy output.  A research target may set
        ``research.record_trace_source`` when its workload already emits the P2S
        primitive-trace schema.  RESTgym uses that path so its own authentication
        and request-rewrite mitmproxy can keep the historical host port ``9090``
        while the *same* P2S compiler/fuzzer handles every Track-B service.
        """
        self.lifecycle.record()
        configured = self.config.research.record_trace_source.strip()
        source = self._rootpath(configured) if configured else self._workpath(self.config.proxy.output_file)
        snapshot_name = self.config.research.record_snapshot_file.strip()
        if not source.exists():
            raise FileNotFoundError(
                f"Configured record trace source does not exist after workload: {source}"
            )
        if snapshot_name:
            snapshot = self._workpath(snapshot_name)
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            if source.resolve() != snapshot.resolve():
                shutil.copy2(source, snapshot)
            print(f"[P2S record] frozen baseline trace -> {snapshot} (source: {source})")

    def coverage(self) -> None:
        """Run the configured target-specific coverage extraction command."""
        self.lifecycle.coverage()

    def cleanup(self) -> None:
        """Run configured cleanup commands."""
        self.lifecycle.cleanup()

    def doctor(self) -> list[str]:
        """Return configuration/environment issues; an empty list means pass."""
        return self.lifecycle.doctor()

    # ------------------------------------------------------------------
    # Adapter construction
    # ------------------------------------------------------------------
    def build_state_adapter(self):
        kind = self.config.target.state_adapter.lower()
        if kind == "postgres":
            hook_path = self.config.postgres.setup_script
            hook = _load_hook(self._rootpath(hook_path)) if hook_path else None
            seed = self.config.postgres.seed_command or None
            return PostgresTemplateAdapter(
                self.config.postgres.active_db,
                self.config.postgres.template_db,
                self.config.postgres.admin_url,
                seed_command=seed,
                pre_snapshot_hook=hook,
                working_directory=str(self.lifecycle.root_dir),
                recreate_active_before_seed=self.config.postgres.recreate_active_before_seed,
                post_seed_commands=self.config.postgres.post_seed_commands,
            )
        if kind == "docker":
            container = self.config.docker.container_name or self.config.target.name
            return DockerRestartAdapter(
                container,
                sleep_time=self.config.docker.restart_sleep_seconds,
            )
        if kind == "command":
            cwd = self.config.command_state.working_directory
            if cwd:
                cwd = str(self._rootpath(cwd))
            else:
                cwd = str(self.lifecycle.root_dir)
            cs = self.config.command_state
            create_command = (
                os.environ.get(cs.create_snapshot_command_env, "")
                if cs.create_snapshot_command_env else cs.create_snapshot_command
            )
            restore_command = (
                os.environ.get(cs.restore_snapshot_command_env, "")
                if cs.restore_snapshot_command_env else cs.restore_snapshot_command
            )
            if cs.restore_snapshot_command_env and not restore_command:
                raise P2SConfigurationError(
                    f"Missing reset command environment variable: {cs.restore_snapshot_command_env}"
                )
            return CommandStateAdapter(
                create_command,
                restore_command,
                working_directory=cwd,
                restore_sleep_seconds=cs.restore_sleep_seconds,
            )
        if kind == "mongo":
            if not self.config.mongo.db_name or not self.config.mongo.mongo_uri:
                raise P2SConfigurationError("mongo state requires [mongo] db_name and mongo_uri")
            return MongoDumpAdapter(
                self.config.mongo.db_name,
                self.config.mongo.mongo_uri,
                self.config.mongo.dump_dir,
            )
        if kind == "file":
            if not self.config.file_state.active_path or not self.config.file_state.backup_path:
                raise P2SConfigurationError(
                    "file state requires [file_state] active_path and backup_path"
                )
            return FileBackupAdapter(
                str(self._rootpath(self.config.file_state.active_path)),
                str(self._rootpath(self.config.file_state.backup_path)),
            )
        if kind == "stateless":
            return StatelessAdapter()
        raise P2SConfigurationError(f"Unknown state_adapter: {kind}")

    def build_executor(self, *, openapi_spec_override: str | os.PathLike[str] | None = None):
        kind = self.config.target.executor_adapter.lower()
        if kind == "ocli":
            oc = self.config.ocli
            profile = oc.profile_name or self.config.target.name
            target_url = oc.api_base_url or self.config.target.base_url
            openapi = str(openapi_spec_override) if openapi_spec_override else (oc.openapi_spec or str(self._spec_path()))
            if oc.openapi_spec and not openapi_spec_override and not oc.openapi_spec.startswith(("http://", "https://")):
                openapi = str(self._rootpath(oc.openapi_spec))
            bearer = os.environ.get(oc.bearer_token_env, "") if oc.bearer_token_env else oc.bearer_token
            if not bearer and oc.bearer_token_file:
                token_path = self._rootpath(oc.bearer_token_file)
                if token_path.exists():
                    bearer = token_path.read_text(encoding="utf-8").strip()
            basic = os.environ.get(oc.basic_auth_env, "") if oc.basic_auth_env else oc.basic_auth
            if not basic and oc.basic_auth_file:
                basic_path = self._rootpath(oc.basic_auth_file)
                if basic_path.exists():
                    basic = basic_path.read_text(encoding="utf-8").strip()
            return OcliExecutorAdapter(
                profile_name=profile,
                target_url=target_url,
                catalog_path=str(self._workpath("ocli_catalog.json")),
                throttle_delay=oc.throttle_delay_seconds,
                timeout=oc.timeout_seconds,
                openapi_spec=openapi,
                bearer_token=bearer,
                basic_auth=basic,
                command_prefix=oc.command_prefix,
            )
        if kind in {"http", "raw_http", "raw-http"}:
            return RawHttpExecutorAdapter(
                base_url=self.config.target.base_url,
                spec_path=str(self._spec_path()),
            )
        raise P2SConfigurationError(f"Unknown executor_adapter: {kind}")

    def build_llm(self):
        kind = self.config.llm.backend.lower()
        api_key = (
            os.environ.get(self.config.llm.api_key_env, "")
            if self.config.llm.api_key_env
            else self.config.llm.api_key
        )
        if kind == "openai_compat":
            return OpenAICompatAdapter(
                self.config.llm.base_url,
                api_key or "no-key",
                self.config.llm.model,
            )
        if kind in {"transformers", "huggingface", "hf"}:
            return TransformersAdapter(self.config.llm.model)
        raise P2SConfigurationError(f"Unknown llm backend: {kind}")

    # ------------------------------------------------------------------
    # Proxy / compiler / engine
    # ------------------------------------------------------------------
    def create_proxy_server(self, *, host: str = "0.0.0.0") -> "P2SProxyServer":
        from .proxy.core_proxy import (
            EndpointResetStrategy, HeaderFlowStrategy, P2SProxyHandler, P2SProxyServer,
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
            mask_sensitive_headers=self.config.proxy.mask_sensitive_headers,
        )

    def run_proxy(self, *, host: str = "0.0.0.0") -> None:
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
        context_path_prefix: Optional[str] = None,
    ) -> tuple[Path, Path]:
        compiler = P2SCompiler(
            swagger_path=str(self._spec_path()),
            context_path_prefix=(
                self.config.target.context_path_prefix
                if context_path_prefix is None
                else context_path_prefix
            ),
        )
        if input_file:
            source = input_file
        else:
            frozen = self.config.research.record_snapshot_file.strip()
            source = frozen if frozen and self._workpath(frozen).exists() else self.config.proxy.output_file
        out = self._workpath(output_file)
        catalog = self._workpath(catalog_file)
        compiler.compile(str(self._workpath(source)), str(out), str(catalog))
        return out, catalog

    def fuzz(
        self,
        *,
        traces_file: str = "compiled_traces.jsonl",
        max_attempts: Optional[int] = None,
        patch_openapi: Optional[bool] = None,
        time_budget_seconds: Optional[int] = None,
        cyclic: Optional[bool] = None,
    ) -> P2SFuzzer:
        patch = (
            self.config.research.patch_openapi_required
            if patch_openapi is None
            else patch_openapi
        )
        runtime_spec = None
        if patch:
            source_spec = self._spec_path()
            runtime_spec = self._workpath(self.config.research.runtime_openapi_file)
            runtime_spec.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_spec, runtime_spec)
            patch_openapi_required(runtime_spec)

        engine = P2SFuzzer(
            self.build_state_adapter(),
            self.build_executor(openapi_spec_override=runtime_spec),
            self.build_llm(),
            build_system_prompt(
                self.config.target.executor_adapter,
                ocli_catalog=self._catalog_text(),
            ),
            str(self._workpath(self.config.target.golden_out)),
            str(self._workpath(self.config.target.silver_out)),
            str(self._workpath(self.config.target.checkpoint_file)),
        )
        budget = (
            self.config.research.time_budget_seconds
            if time_budget_seconds is None
            else time_budget_seconds
        )
        cyclic_mode = self.config.research.cyclic if cyclic is None else cyclic
        if cyclic_mode and self.config.research.clear_checkpoint_for_cyclic:
            cp = self._workpath(self.config.target.checkpoint_file)
            if cp.exists():
                cp.unlink()
        engine.run_all(
            traces_file=str(self._workpath(traces_file)),
            max_attempts=max_attempts or self.config.llm.max_attempts,
            time_budget_seconds=budget,
            cyclic=cyclic_mode,
            reset_before_each_target=self.config.research.reset_before_each_target,
            reset_before_each_flow=self.config.research.reset_before_each_flow,
            pre_step_replay=self.config.research.pre_step_replay,
            require_attack_flag_for_2xx=self.config.research.require_attack_flag_for_2xx,
        )
        return engine

    def generate_data(
        self,
        *,
        traces_file: str = "compiled_traces.jsonl",
        max_attempts: Optional[int] = None,
    ) -> P2SDataGenerator:
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
            reset_before_each_flow=self.config.research.reset_before_each_flow,
            pre_step_replay=self.config.research.pre_step_replay,
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
        output = self._workpath(output_file)
        prepare_stratified_dataset(
            golden_file=str(self._workpath(golden_file or self.config.target.golden_out)),
            silver_file=str(self._workpath(silver_file or self.config.target.silver_out)),
            output_file=str(output),
            max_seq_length=max_seq_length,
            seed=seed,
        )
        return output


P2SClient = P2S

__all__ = [
    "P2S",
    "P2SClient",
    "P2SError",
    "P2SConfigurationError",
    "patch_openapi_required",
]
