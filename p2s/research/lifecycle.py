"""Framework-native lifecycle and environment preparation.

The historical research used target-specific setup snippets.  This module moves
those differences into configuration so the same public P2S proxy/compiler/
engine can execute every P2S research operation.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

from ..config import PatchConfig, P2SConfig
from .shell import run_shell


@dataclass
class PatchResult:
    path: str
    kind: str
    changed: bool
    message: str


class ResearchLifecycle:
    def __init__(self, config: P2SConfig, *, config_dir: Path, workdir: Path):
        self.config = config
        self.config_dir = Path(config_dir).resolve()
        self.workdir = Path(workdir).resolve()
        root_value = os.path.expandvars(os.path.expanduser(config.research.root_dir or "."))
        root = Path(root_value)
        self.root_dir = (root if root.is_absolute() else self.config_dir / root).resolve()

    def resolve(self, value: str | os.PathLike[str]) -> Path:
        expanded = os.path.expandvars(os.path.expanduser(str(value)))
        p = Path(expanded)
        return p if p.is_absolute() else self.root_dir / p

    # ------------------------------------------------------------------
    # File patches
    # ------------------------------------------------------------------
    def apply_patch(self, patch: PatchConfig) -> PatchResult:
        path = self.resolve(patch.path)
        kind = patch.kind.lower().strip()
        if not patch.path:
            raise ValueError("Patch path cannot be empty")

        if kind == "write":
            path.parent.mkdir(parents=True, exist_ok=True)
            current = path.read_text(encoding="utf-8") if path.exists() else None
            changed = current != patch.content
            if changed:
                path.write_text(patch.content, encoding="utf-8")
            return PatchResult(str(path), kind, changed, "written" if changed else "already exact")

        if kind == "append":
            path.parent.mkdir(parents=True, exist_ok=True)
            current = path.read_text(encoding="utf-8") if path.exists() else ""
            if patch.content in current:
                return PatchResult(str(path), kind, False, "content already present")
            with path.open("a", encoding="utf-8") as f:
                if current and not current.endswith("\n"):
                    f.write("\n")
                f.write(patch.content)
                if patch.content and not patch.content.endswith("\n"):
                    f.write("\n")
            return PatchResult(str(path), kind, True, "content appended")

        if kind == "regex_replace":
            if not path.exists():
                if patch.required:
                    raise FileNotFoundError(path)
                return PatchResult(str(path), kind, False, "optional file missing")
            text = path.read_text(encoding="utf-8")
            limit = patch.count if patch.count and patch.count > 0 else 0
            updated, n = re.subn(patch.find, patch.replace, text, count=limit, flags=re.MULTILINE)
            if n == 0:
                # Idempotency: if the desired replacement already appears, pass.
                if patch.replace and patch.replace in text:
                    return PatchResult(str(path), kind, False, "replacement already present")
                if patch.required:
                    raise RuntimeError(
                        f"Required regex patch did not match {path}: {patch.find[:120]!r}"
                    )
                return PatchResult(str(path), kind, False, "optional regex did not match")
            if updated == text:
                return PatchResult(str(path), kind, False, "replacement already exact")
            path.write_text(updated, encoding="utf-8")
            return PatchResult(str(path), kind, True, f"regex replacement applied ({n} match(es))")

        if kind != "replace":
            raise ValueError(f"Unsupported patch kind: {patch.kind}")
        if not path.exists():
            if patch.required:
                raise FileNotFoundError(path)
            return PatchResult(str(path), kind, False, "optional file missing")

        text = path.read_text(encoding="utf-8")
        if patch.replace and patch.replace in text and patch.find not in text:
            return PatchResult(str(path), kind, False, "replacement already present")
        if patch.find not in text:
            if patch.required:
                raise RuntimeError(
                    f"Required patch text not found in {path}: {patch.find[:120]!r}"
                )
            return PatchResult(str(path), kind, False, "optional match not found")

        count = patch.count if patch.count and patch.count > 0 else -1
        updated = text.replace(patch.find, patch.replace, count)
        path.write_text(updated, encoding="utf-8")
        return PatchResult(str(path), kind, True, "replacement applied")

    def apply_patches(self) -> list[PatchResult]:
        results = [self.apply_patch(patch) for patch in self.config.patches]
        for result in results:
            status = "changed" if result.changed else "ok"
            print(f"[P2S patch:{status}] {result.path}: {result.message}")
        return results

    # ------------------------------------------------------------------
    # Commands / readiness
    # ------------------------------------------------------------------
    def run_command(self, command: str, *, check: bool = True) -> subprocess.CompletedProcess:
        return run_shell(command, check=check, cwd=self.root_dir, text=True)

    def run_commands(self, commands: list[str]) -> None:
        for command in commands:
            if command.strip():
                print(f"[P2S lifecycle] $ {command}")
                self.run_command(command)

    def wait_ready(self) -> bool:
        url = self.config.research.readiness_url.strip()
        if not url:
            return True
        timeout = max(1, int(self.config.research.readiness_timeout_seconds))
        interval = max(0.1, float(self.config.research.readiness_interval_seconds))
        deadline = time.monotonic() + timeout
        last_error = None
        while time.monotonic() < deadline:
            try:
                req = Request(url, headers={"User-Agent": "p2s-framework-repro/1.2"})
                with urlopen(req, timeout=min(5, timeout)) as resp:
                    if 200 <= int(resp.status) < 500:
                        print(f"[P2S lifecycle] target ready: {url} -> {resp.status}")
                        return True
            except Exception as exc:  # readiness polling is intentionally permissive
                last_error = exc
            time.sleep(interval)
        raise TimeoutError(f"Target did not become ready within {timeout}s: {url} ({last_error})")

    # ------------------------------------------------------------------
    # Native OpenAPI acquisition / sanitisation
    # ------------------------------------------------------------------
    @staticmethod
    def _load_openapi_bytes(raw: bytes) -> dict:
        text = raw.decode("utf-8")
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            try:
                import yaml
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError("YAML OpenAPI input requires PyYAML") from exc
            obj = yaml.safe_load(text)
        if not isinstance(obj, dict):
            raise ValueError("OpenAPI document must decode to an object")
        return obj

    def fetch_openapi(self) -> Path | None:
        cfg = self.config.openapi_setup
        if not cfg.source_url:
            return None
        req = Request(cfg.source_url, headers={"User-Agent": "p2s-framework-repro/1.2"})
        with urlopen(req, timeout=30) as resp:
            spec = self._load_openapi_bytes(resp.read())

        if cfg.server_url:
            spec["servers"] = [{"url": cfg.server_url}]
        paths = spec.setdefault("paths", {})
        for path_name in cfg.remove_paths:
            paths.pop(path_name, None)
        for entry in cfg.remove_operations:
            method, sep, path_name = entry.strip().partition(" ")
            if not sep:
                raise ValueError(
                    f"openapi_setup.remove_operations entry must be 'METHOD /path': {entry!r}"
                )
            item = paths.get(path_name)
            if isinstance(item, dict):
                item.pop(method.lower(), None)
                # Keep the path item if it still contains parameters or another operation.
                if not item:
                    paths.pop(path_name, None)

        output_name = cfg.output_file or self.config.target.openapi_spec
        output = self.resolve(output_name)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[P2S openapi] {cfg.source_url} -> {output}")
        return output

    # ------------------------------------------------------------------
    # Native controlled credential acquisition
    # ------------------------------------------------------------------
    def acquire_auth(self) -> Path | None:
        cfg = self.config.auth
        mode = cfg.mode.strip().lower()
        if not mode:
            return None
        if mode != "bearer_login":
            raise ValueError(f"Unsupported auth.mode: {cfg.mode}")
        if not cfg.login_url:
            raise ValueError("auth.login_url is required for bearer_login")
        self.run_commands(cfg.pre_login_commands)

        payload = json.dumps(cfg.login_body).encode("utf-8")
        req = Request(
            cfg.login_url,
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "p2s-framework-repro/1.2"},
            method="POST",
        )
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        token = data
        for component in cfg.token_json_field.split("."):
            if isinstance(token, dict):
                token = token.get(component)
            else:
                token = None
            if token is None:
                break
        if not isinstance(token, str) or not token.strip():
            raise RuntimeError(
                f"Bearer token field {cfg.token_json_field!r} missing from login response"
            )
        output = self.resolve(cfg.token_output_file)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(token.strip(), encoding="utf-8")
        try:
            output.chmod(0o600)
        except OSError:
            pass
        print(f"[P2S auth] controlled bearer token -> {output}")
        return output

    # ------------------------------------------------------------------
    # Composite lifecycle
    # ------------------------------------------------------------------
    def prepare(self) -> list[PatchResult]:
        self.root_dir.mkdir(parents=True, exist_ok=True)
        results = self.apply_patches()
        self.run_commands(self.config.research.prepare_commands)
        self.wait_ready()
        self.fetch_openapi()
        self.acquire_auth()
        return results

    def record(self) -> None:
        command = self.config.research.record_command.strip()
        if not command:
            raise RuntimeError("No research.record_command configured")
        self.run_command(command)

    def coverage(self) -> None:
        command = self.config.research.coverage_command.strip()
        if not command:
            raise RuntimeError("No research.coverage_command configured")
        self.run_command(command)

    def cleanup(self) -> None:
        self.run_commands(self.config.research.cleanup_commands)

    def doctor(self) -> list[str]:
        issues: list[str] = []
        if not self.root_dir.exists():
            issues.append(f"research.root_dir does not exist: {self.root_dir}")
        spec = self.resolve(self.config.target.openapi_spec)
        if (
            not spec.exists()
            and not self.config.openapi_setup.source_url
            and not str(self.config.target.openapi_spec).startswith(("http://", "https://"))
        ):
            issues.append(f"OpenAPI spec not found: {spec}")
        if self.config.target.executor_adapter.lower() == "ocli" and shutil.which("ocli") is None:
            issues.append("ocli executable not found on PATH")
        kind = self.config.target.state_adapter.lower()
        if kind == "command":
            cs = self.config.command_state
            restore = cs.restore_snapshot_command
            if cs.restore_snapshot_command_env:
                restore = os.environ.get(cs.restore_snapshot_command_env, "")
                if not restore:
                    issues.append(
                        f"state_adapter=command requires environment variable "
                        f"{cs.restore_snapshot_command_env} to contain the reset command"
                    )
            if not restore and not cs.restore_snapshot_command_env:
                issues.append(
                    "state_adapter=command requires command_state.restore_snapshot_command "
                    "or restore_snapshot_command_env"
                )
        if kind == "docker" and not (self.config.docker.container_name or self.config.target.name):
            issues.append("state_adapter=docker requires docker.container_name or target.name")
        if self.config.auth.mode and not self.config.auth.login_url:
            issues.append("auth.mode is set but auth.login_url is empty")
        if self.config.ocli.bearer_token_file:
            token_path = self.resolve(self.config.ocli.bearer_token_file)
            if not token_path.exists() and not self.config.auth.mode:
                issues.append(f"OCLI bearer token file not found: {token_path}")
        return issues
