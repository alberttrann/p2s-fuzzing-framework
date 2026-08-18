import json
import re
import shlex
import urllib.parse
import os
from pathlib import Path

class P2SCompiler:
    def __init__(self, swagger_path: str, context_path_prefix: str = "/api"):
        self.context_path_prefix = context_path_prefix
        self.spec = self._load_spec(swagger_path)
        self.routes = self._build_router()
        self.catalog = {}

    @staticmethod
    def _load_spec(swagger_path: str) -> dict:
        """Load OpenAPI/Swagger from JSON or YAML.

        RESTgym mixes JSON and YAML specifications, so framework-native Track-B
        reproduction must not depend on a target-specific compiler just to parse
        the contract format.
        """
        text = Path(swagger_path).read_text(encoding="utf-8")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            try:
                import yaml
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError(
                    "YAML OpenAPI input requires PyYAML; install p2s-framework>=1.2"
                ) from exc
            data = yaml.safe_load(text)
            if not isinstance(data, dict):
                raise ValueError(f"OpenAPI document is not an object: {swagger_path}")
            return data

    def _resolve_schema(self, schema: dict) -> dict:
        if not isinstance(schema, dict):
            return {}
        ref = schema.get("$ref", "")
        if ref.startswith("#/components/schemas/"):
            return self.spec.get("components", {}).get("schemas", {}).get(ref.rsplit("/", 1)[-1], {})
        if ref.startswith("#/definitions/"):
            return self.spec.get("definitions", {}).get(ref.rsplit("/", 1)[-1], {})
        return schema

    def _request_body_schema(self, details: dict) -> tuple[dict, str]:
        request_body = details.get("requestBody", {}) or {}
        content = request_body.get("content", {}) if isinstance(request_body, dict) else {}
        for media in ("application/json", "application/x-www-form-urlencoded", "multipart/form-data"):
            if media in content:
                return self._resolve_schema(content[media].get("schema", {}) or {}), media
        # Swagger/OpenAPI 2 body parameter fallback.
        for param in details.get("parameters", []) or []:
            if param.get("in") == "body":
                return self._resolve_schema(param.get("schema", {}) or {}), "application/json"
        return {}, ""

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
        schema, media_type = self._request_body_schema(details)
        if schema:
            for pname, pschema in schema.get("properties", {}).items():
                flags[pname] = {
                    "in": "body", "required": pname in schema.get("required", []),
                    "type": self._resolve_schema_type(pschema),
                    "description": pschema.get("description", ""),
                    "media_type": media_type,
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
                    body_schema, media_type = self._request_body_schema(matched["details"])
                    if isinstance(body, str) and media_type == "application/x-www-form-urlencoded":
                        body = dict(urllib.parse.parse_qsl(body, keep_blank_values=True))
                    if body is not None and isinstance(body, dict):
                        has_defined_props = bool(body_schema.get("properties"))
                        if has_defined_props:
                            for k, v in body.items():
                                val_str = json.dumps(v) if isinstance(v, (dict, list, bool)) \
                                          or v is None else str(v)
                                flags.append(f"--{k} {shlex.quote(val_str)}")
                        else:
                            # Sparse/opaque schema fallback retained from the source experiment.
                            flags.append(f"--body {shlex.quote(json.dumps(body))}")
                    elif body not in (None, ""):
                        flags.append(f"--body {shlex.quote(str(body))}")

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
