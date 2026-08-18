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
                 catalog_path: str = "ocli_catalog.json",
                 openapi_spec: str = "",
                 bearer_token: str = "",
                 basic_auth: str = "",
                 command_prefix: str = ""):
        self.profile_name = profile_name
        self.target_url = target_url.rstrip("/")
        self.throttle_delay = throttle_delay
        self.timeout = timeout
        self.openapi_spec = openapi_spec or f"{self.target_url}/v3/api-docs"
        self.profile_bearer_token = bearer_token or ""
        self.basic_auth = basic_auth or ""
        self.command_prefix = command_prefix or ""

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
            args = [
                "ocli", "profiles", "add", self.profile_name,
                "--api-base-url", self.target_url,
                "--openapi-spec", self.openapi_spec,
            ]
            if self.basic_auth:
                args += ["--api-basic-auth", self.basic_auth]
            else:
                args += ["--api-bearer-token", self.profile_bearer_token]
            args += ["--command-prefix", self.command_prefix]
            subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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

        effective_bearer = bearer_token or self.profile_bearer_token
        if effective_bearer and "--api-bearer-token" not in cmd_str:
            cmd_str += f" --api-bearer-token {shlex.quote(effective_bearer)}"
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
