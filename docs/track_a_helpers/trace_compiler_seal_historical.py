#!/usr/bin/env python3
"""
SealHackathon Trace Compiler
Converts primitive_traces.jsonl → compiled_traces.jsonl with ocli commands.

Two fixes over the original trace_compiler.py:
  1. Strips the /api context-path prefix before OpenAPI route matching.
  2. Skips steps whose resolved path contains // (empty path param — the
     shell script variable was empty when that curl ran).
"""

import json
import re
import shlex
import urllib.parse
import sys
import os

BACKEND_DIR       = os.path.dirname(os.path.abspath(__file__))
SWAGGER_FILE      = os.path.join(BACKEND_DIR, "swagger.json")
INPUT_TRACE_FILE  = os.path.join(BACKEND_DIR, "primitive_traces.jsonl")
OUTPUT_TRACE_FILE = os.path.join(BACKEND_DIR, "compiled_traces.jsonl")
CATALOG_FILE      = os.path.join(BACKEND_DIR, "seal_ocli_catalog.json")

# The Spring Boot context-path prefix to strip before OpenAPI matching
CONTEXT_PATH_PREFIX = "/api"


class SealTraceCompiler:
    def __init__(self, swagger_path):
        self.openapi_spec = self._load_json(swagger_path)
        self.routes       = self._build_regex_router()
        self.catalog      = {}   # command_name → {flags, description}

    def _load_json(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"[ERROR] Cannot find {path}")
            print(f"  Run: curl -o swagger.json http://localhost:8080/api/v3/api-docs")
            sys.exit(1)

    def _build_regex_router(self):
        routes = []
        paths  = self.openapi_spec.get("paths", {})
        for openapi_path, methods in paths.items():
            # Convert {param} → named regex group
            regex_str = re.sub(r"\{([^}]+)\}", r"(?P<\1>[^/]+)", openapi_path)
            regex_pat = re.compile(f"^{regex_str}$")
            for method, details in methods.items():
                if method.lower() in ("get","post","put","patch","delete"):
                    routes.append({
                        "openapi_path": openapi_path,
                        "method":       method.upper(),
                        "regex":        regex_pat,
                        "details":      details,
                    })
        print(f"[COMPILER] Loaded {len(routes)} routes from Swagger.")
        return routes

    def _get_ocli_command_name(self, openapi_path, method):
        paths = self.openapi_spec.get("paths", {})
        path_item = paths.get(openapi_path, {})

        methods = ["get", "post", "put", "delete", "patch", "head", "options", "trace"]
        defined_methods = [m for m in methods if m in path_item]

        clean = openapi_path.strip("/")
        clean = re.sub(r"\{([^}]+)\}", r"\1", clean)   # {id} → id
        clean = clean.replace("/", "_")                # ONLY this. No '-' or '.' replacement.

        if len(defined_methods) > 1:
            return f"ocli {clean}_{method.lower()}"
        else:
            return f"ocli {clean}"
    def _resolve_schema_type(self, schema):
        """
        Resolves a parameter's declared type, following a single-level $ref
        into components/schemas if present (e.g. the Pageable schema used
        by 'pageable'-named query params). Without this, any $ref-typed
        param silently defaults to 'string' since there's no inline 'type'
        key to read.
        """
        if not schema:
            return "string"
        if "$ref" in schema:
            m = re.match(r"^#/components/schemas/(.+)$", schema["$ref"])
            if m:
                resolved = self.openapi_spec.get("components", {}).get("schemas", {}).get(m.group(1), {})
                return resolved.get("type", "string")
            return "string"
        return schema.get("type", "string")
    def _build_catalog_entry(self, command_name, openapi_path, method, details):
        """Build an entry for the ocli catalog JSON."""
        params = details.get("parameters", [])
        request_body = details.get("requestBody", {})
        flags = {}

        for p in params:
            pname = p.get("name", "")
            ploc  = p.get("in", "")
            flags[pname] = {
                "in":         ploc,
                "required":   p.get("required", False),
                "type":       self._resolve_schema_type(p.get("schema", {})),
                "description":p.get("description", ""),
            }

        if request_body:
            content = request_body.get("content", {})
            schema  = (content.get("application/json", {})
                               .get("schema", {}))
            props = schema.get("properties", {})
            required_body = schema.get("required", [])
            for pname, pschema in props.items():
                flags[pname] = {
                    "in":         "body",
                    "required":   pname in required_body,
                    "type":       pschema.get("type", "string"),
                    "description":pschema.get("description", ""),
                }

        self.catalog[command_name] = {
            "openapi_path": openapi_path,
            "method":       method,
            "summary":      details.get("summary", ""),
            "flags":        flags,
        }

    def compile_step(self, trace_step):
        request  = trace_step.get("request", {})
        method   = request.get("method", "").upper()
        raw_path = request.get("path", "")

        # Parse URL
        parsed     = urllib.parse.urlsplit(raw_path)
        full_path  = parsed.path
        query_dict = dict(urllib.parse.parse_qsl(parsed.query))

        # Skip health checks
        if full_path.rstrip("/") in ("/health", "/api/health", "/actuator/health"):
            return None

        # ── FIX 1: strip /api context-path prefix ────────────────────────────
        if full_path.startswith(CONTEXT_PATH_PREFIX):
            openapi_path_candidate = full_path[len(CONTEXT_PATH_PREFIX):]
        else:
            openapi_path_candidate = full_path

        # ── FIX 2: skip steps with empty path params (shell var was unset) ───
        if "//" in openapi_path_candidate:
            print(f"[SKIP] Empty path param in: {method} {full_path}  (shell variable was unset)")
            return None

        # Empty-trailing-slash normalisation
        openapi_path_candidate = openapi_path_candidate.rstrip("/") or "/"

        # ── Route matching ────────────────────────────────────────────────────
        matched_route = None
        path_params   = {}
        for route in self.routes:
            if route["method"] == method:
                m = route["regex"].match(openapi_path_candidate)
                if m:
                    matched_route = route
                    path_params   = m.groupdict()
                    break

        if not matched_route:
            print(f"[SKIP] No route match: {method} {full_path}  (stripped: {openapi_path_candidate})")
            return None

        openapi_path = matched_route["openapi_path"]
        ocli_cmd     = self._get_ocli_command_name(openapi_path, method)
        self._build_catalog_entry(ocli_cmd, openapi_path, method, matched_route["details"])

        # ── Assemble flags ────────────────────────────────────────────────────
        flags = []

        for k, v in path_params.items():
            flags.append(f"--{k} {shlex.quote(str(v))}")

        for k, v in query_dict.items():
            flags.append(f"--{k} {shlex.quote(str(v))}")

        body = request.get("body")
        if body and isinstance(body, dict):
            for k, v in body.items():
                if isinstance(v, (dict, list, bool)) or v is None:
                    val_str = json.dumps(v)
                else:
                    val_str = str(v)
                flags.append(f"--{k} {shlex.quote(val_str)}")

        compiled_command = f"{ocli_cmd} {' '.join(flags)}".strip()

        trace_step["ocli_command"]  = compiled_command
        trace_step["openapi_path"]  = openapi_path
        return trace_step

    def run(self):
        print(f"[COMPILER] Reading traces from  : {INPUT_TRACE_FILE}")
        print(f"[COMPILER] Writing compiled to  : {OUTPUT_TRACE_FILE}")
        print(f"[COMPILER] Writing catalog to   : {CATALOG_FILE}")

        compiled = []
        skipped_route  = 0
        skipped_empty  = 0
        total = 0

        with open(INPUT_TRACE_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip(): continue
                total += 1
                step = json.loads(line)
                result = self.compile_step(step)
                if result:
                    compiled.append(result)
                else:
                    # Distinguish skip reasons
                    raw_path = step.get("request", {}).get("path", "")
                    if "//" in raw_path:
                        skipped_empty += 1
                    else:
                        skipped_route += 1

        # Write compiled traces
        with open(OUTPUT_TRACE_FILE, "w", encoding="utf-8") as f:
            for step in compiled:
                f.write(json.dumps(step, ensure_ascii=False) + "\n")

        # Write ocli catalog
        with open(CATALOG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.catalog, f, ensure_ascii=False, indent=2)

        print(f"\n[COMPILER] Results:")
        print(f"  Total raw steps     : {total}")
        print(f"  Compiled OK         : {len(compiled)}")
        print(f"  Skipped (no route)  : {skipped_route}")
        print(f"  Skipped (empty UUID): {skipped_empty}  ← fix shell script variable exports")
        print(f"\n  compiled_traces.jsonl : {OUTPUT_TRACE_FILE}")
        print(f"  seal_ocli_catalog.json: {CATALOG_FILE}")

        if skipped_empty > 0:
            print(f"\n[WARN] {skipped_empty} steps had empty path params (// in URL).")
            print(f"  This means a shell variable like $UNI_ID or $ROUND_ID was empty")
            print(f"  when curl ran. Check that each sfN_ function exports its IDs")
            print(f"  before the next function uses them.")


if __name__ == "__main__":
    compiler = SealTraceCompiler(SWAGGER_FILE)
    compiler.run()
