#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════════════════
# eval_student_p2s_engine.py  (FINAL — all 10 audit fixes integrated)
# P2S Evaluation Engine with switchable inference backends.
#
# Backends:
#   "transformers"  → Student model (merged-4bit or merged-16bit, local GPU)
#   "llamacpp"      → llama-server (fine-tuned GGUF via llama.cpp)
#   "lm_studio"     → LM Studio / any OpenAI-compatible local server
#   "openai"        → DeepSeek, GPT-4o, etc.
#   "anthropic"     → Claude Sonnet, Claude Opus etc.
#
# Output files are prefixed with the backend name so runs never collide.
# ═══════════════════════════════════════════════════════════════════════════════

import json, os, re, shlex, subprocess, sys, requests
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from collections import Counter

GLOBAL_COORD_TOKEN = None

# ─── OPTIMIZATION: Cache Git Bash path once ──────────────────────────────────
CACHED_BASH_PATH = None
if sys.platform == "win32":
    import shutil
    CACHED_BASH_PATH = shutil.which("bash")
    if not CACHED_BASH_PATH:
        for _p in [
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files\Git\usr\bin\bash.exe",
            os.path.expanduser(r"~\AppData\Local\Programs\Git\bin\bash.exe")
        ]:
            if os.path.exists(_p):
                CACHED_BASH_PATH = _p
                break

# ╔══════════════════════════════════════════════════════════════════════════════
# ║  MONKEY-PATCHES FOR PYTORCH & SAFETENSORS (QWEN3.5 WINDOWS-STABLE BYPASS)
# ╚══════════════════════════════════════════════════════════════════════════════

def apply_evaluation_runtime_patches():
    import torch
    import torch.nn.init as init
    import safetensors
    import safetensors.torch

    print("\n[PATCH] Initializing PyTorch weight-init compatibility patches...")

    if hasattr(init, "_no_grad_normal_"):
        orig = init._no_grad_normal_
        def patched(tensor, mean=0., std=1., generator=None):
            return tensor if tensor.dtype in (torch.uint8, torch.int8) else orig(tensor, mean, std, generator)
        init._no_grad_normal_ = patched

    if hasattr(init, "normal_"):
        orig = init.normal_
        def patched(tensor, mean=0., std=1., *, generator=None):
            return tensor if tensor.dtype in (torch.uint8, torch.int8) else orig(tensor, mean, std, generator=generator)
        init.normal_ = patched

    try:
        import transformers.initialization as tf_init
        if hasattr(tf_init, "TORCH_INIT_FUNCTIONS") and "normal_" in tf_init.TORCH_INIT_FUNCTIONS:
            orig = tf_init.TORCH_INIT_FUNCTIONS["normal_"]
            def patched(tensor, mean=0., std=1., generator=None):
                return tensor if tensor.dtype in (torch.uint8, torch.int8) else orig(tensor, mean, std, generator)
            tf_init.TORCH_INIT_FUNCTIONS["normal_"] = patched
    except ImportError:
        pass

    print("[PATCH] Initializing Safetensors double-prefix key mapper...")

    orig_load_file = safetensors.torch.load_file
    def patched_load_file(filename, device="cpu"):
        sd = orig_load_file(filename, device=device)
        PREFIX = "model.language_model.language_model."
        return {("model." + k[len(PREFIX):] if k.startswith(PREFIX) else k): v for k, v in sd.items()}
    safetensors.torch.load_file = patched_load_file

    orig_safe_open = safetensors.safe_open
    class PatchedSafeOpen:
        def __init__(self, *a, **kw):
            self.handle = orig_safe_open(*a, **kw)
            PREFIX = "model.language_model.language_model."
            self._keys_list, self._fwd = [], {}
            for k in self.handle.keys():
                mk = ("model." + k[len(PREFIX):]) if k.startswith(PREFIX) else k
                self._keys_list.append(mk); self._fwd[mk] = k
        def keys(self):          return self._keys_list
        def get_tensor(self, k): return self.handle.get_tensor(self._fwd.get(k, k))
        def get_slice(self, k):  return self.handle.get_slice(self._fwd.get(k, k))
        def __enter__(self):     return self
        def __exit__(self, *a):  pass
    safetensors.safe_open = PatchedSafeOpen
    print("[PATCH] Patches successfully injected into runtime.\n")

apply_evaluation_runtime_patches()

# ╔══════════════════════════════════════════════════════════════════════════════
# ║  MODULE-LEVEL HELPERS  (FIX #5, #6, #7, #10 — hoisted out of hot loop)
# ╚══════════════════════════════════════════════════════════════════════════════

def _deep_unescape(s):
    """Iteratively strip double/triple-escaped quotes."""
    prev = None
    while prev != s:
        prev = s
        s = s.replace('\\\\"', '"').replace('\\"', '"').replace("\\'", "'")
    return s

def _build_assistant_turn(reasoning, mutated_cmd, predicted_status, actual_status):
    """Construct the assistant turn for training-record format.
    Uses predicted_status for the ASSERT line when available, falls back to actual."""
    actual_int = int(actual_status) if str(actual_status).isdigit() else actual_status
    assert_val = predicted_status if predicted_status is not None else actual_int
    return (
        f"<think>\n{reasoning}\n</think>\n\n"
        f"```bash\n{mutated_cmd}\n```\n"
        f"# ASSERT: status == {assert_val}"
    )

_REFUSAL_PATTERNS = re.compile(
    r'cannot\s+assist|unable\s+to\s+help|'
    r'violates?\s+(?:safety|policy|guidelines)|'
    r'not\s+(?:able|permitted)\s+to\s+(?:generate|create|help)|'
    r'decline\s+to|inappropriate\s+to',
    re.IGNORECASE
)

_VECTOR_PATTERNS = [
    (re.compile(r'null.?byte|\\x00|%00', re.I),                      'Null-Byte'),
    (re.compile(r'type.?confusion|integer.*string', re.I),            'Type Confusion'),
    (re.compile(r'integer.?boundar|2147483647|9223372', re.I),        'Integer Boundary'),
    (re.compile(r'string.?extreme|empty.?string|50.?000', re.I),      'String Extremes'),
    (re.compile(r'sql.?inject|sqli|or.1.=.1', re.I),                 'SQLi'),
    (re.compile(r'xss|script.*alert', re.I),                          'XSS'),
    (re.compile(r'encod|url.?encod|double.?encod', re.I),             'Encoding'),
    (re.compile(r'omit|mandatory|missing.?field|required', re.I),     'Mandatory Omission'),
    (re.compile(r'conflict|mutually.?exclusive', re.I),               'Parameter Conflict'),
    (re.compile(r'idor|path.?travers|resource.?id', re.I),            'IDOR'),
    (re.compile(r'mass.?assign|read.?only|owasp.?api3', re.I),        'Mass Assignment'),
    (re.compile(r'bola|bfla|rbac|bypass|escalat|unauthorized', re.I), 'BOLA/BFLA'),
    (re.compile(r'business.?flow|skip.*step|prerequisite', re.I),     'Business Flow'),
    (re.compile(r'replay|idempoten|concurrent', re.I),                'Replay'),
    (re.compile(r'desync|mismatch.*uuid|context', re.I),              'Context Desync'),
    (re.compile(r'premature|draft|pending.*transit', re.I),           'Premature Progression'),
]

def _classify_vector(reasoning_text):
    for pattern, label in _VECTOR_PATTERNS:
        if pattern.search(reasoning_text or ""):
            return label
    return "Unknown"

# ╔══════════════════════════════════════════════════════════════════════════════
# ║  SECTION 1 — BACKEND SELECTION
# ╚══════════════════════════════════════════════════════════════════════════════

INFERENCE_BACKEND = "llamacpp"  # "transformers" | "llamacpp" | "lm_studio" | "openai" | "anthropic"

TRANSFORMERS_MODEL_PATH = "minhhungg/qwen35-9b-p2s-merged-4bit"

LLAMACPP_BASE_URL = "http://localhost:8081/v1"
LLAMACPP_MODEL    = "qwen35-9b-p2s-Q8_0"

LM_STUDIO_BASE_URL = "http://localhost:1234/v1"
LM_STUDIO_API_KEY  = "lm-studio"
LM_STUDIO_MODEL    = "qwen3.5-9b"

OPENAI_BASE_URL = "https://api.deepseek.com"
OPENAI_API_KEY  = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL    = "deepseek-v4-flash"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL   = "claude-sonnet-4-5"

# ╔══════════════════════════════════════════════════════════════════════════════
# ║  SECTION 2 — FILE / DB CONFIG
# ╚══════════════════════════════════════════════════════════════════════════════

COMPILED_TRACES_FILE = "compiled_traces.jsonl"
CATALOG_FILE         = "seal_ocli_catalog.json"
ADMIN_DB_URL         = "postgresql://postgres:postgres@localhost:5432/postgres"
ACTIVE_DB_NAME       = "seal_hackathon"
TEMPLATE_DB_NAME     = "seal_hackathon_snap"
MAX_ATTEMPTS         = 6

# ╔══════════════════════════════════════════════════════════════════════════════
# ║  SECTION 3 — BACKEND INITIALISATION
# ╚══════════════════════════════════════════════════════════════════════════════

def _init_transformers():
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    print(f"[BACKEND] transformers | model: {TRANSFORMERS_MODEL_PATH}")
    tok = AutoTokenizer.from_pretrained(TRANSFORMERS_MODEL_PATH)
    mdl = AutoModelForCausalLM.from_pretrained(
        TRANSFORMERS_MODEL_PATH, device_map="auto",
        torch_dtype=torch.bfloat16, trust_remote_code=False)
    mdl.eval()
    print(f"[DIAGNOSTIC] GPU mem: {torch.cuda.memory_allocated()/1e9:.2f}GB alloc, "
          f"{torch.cuda.memory_reserved()/1e9:.2f}GB reserved")
    return tok, mdl

def _init_openai_compat(base_url, api_key, model_name, label):
    try: from openai import OpenAI
    except ImportError: sys.exit("[BACKEND] pip install openai")
    print(f"[BACKEND] {label} | {base_url} | {model_name}")
    return OpenAI(base_url=base_url, api_key=api_key)

def _init_anthropic():
    try: import anthropic as _a
    except ImportError: sys.exit("[BACKEND] pip install anthropic")
    print(f"[BACKEND] anthropic | {ANTHROPIC_MODEL}")
    return _a.Anthropic(api_key=ANTHROPIC_API_KEY)

_hf_tokenizer = _hf_model = None
_openai_client = _anthropic_client = None

if   INFERENCE_BACKEND == "transformers": _hf_tokenizer, _hf_model = _init_transformers()
elif INFERENCE_BACKEND == "llamacpp":     _openai_client = _init_openai_compat(LLAMACPP_BASE_URL, "no-key", LLAMACPP_MODEL, "llamacpp")
elif INFERENCE_BACKEND == "lm_studio":    _openai_client = _init_openai_compat(LM_STUDIO_BASE_URL, LM_STUDIO_API_KEY, LM_STUDIO_MODEL, "lm_studio")
elif INFERENCE_BACKEND == "openai":       _openai_client = _init_openai_compat(OPENAI_BASE_URL, OPENAI_API_KEY, OPENAI_MODEL, "openai")
elif INFERENCE_BACKEND == "anthropic":    _anthropic_client = _init_anthropic()
else: sys.exit(f"Unknown backend: {INFERENCE_BACKEND}")

_PREFIX             = INFERENCE_BACKEND
GOLDEN_DATASET_FILE = f"{_PREFIX}_golden_dataset.jsonl"
SILVER_DATASET_FILE = f"{_PREFIX}_silver_dataset.jsonl"
CHECKPOINT_FILE     = f"{_PREFIX}_processed_flows.txt"

# ╔══════════════════════════════════════════════════════════════════════════════
# ║  SECTION 4 — UNIFIED INFERENCE CALL
# ╚══════════════════════════════════════════════════════════════════════════════

def _get_backend_config():
    if   INFERENCE_BACKEND == "llamacpp":  return LLAMACPP_BASE_URL, "no-key", LLAMACPP_MODEL
    elif INFERENCE_BACKEND == "lm_studio": return LM_STUDIO_BASE_URL, LM_STUDIO_API_KEY, LM_STUDIO_MODEL
    elif INFERENCE_BACKEND == "openai":    return OPENAI_BASE_URL, OPENAI_API_KEY, OPENAI_MODEL
    return None, None, None

def call_llm(messages, attempt):
    temp = 0.1 if attempt == 0 else min(0.1 + attempt * 0.15, 0.8)
    if   INFERENCE_BACKEND == "transformers":              return _call_transformers(messages, temp)
    elif INFERENCE_BACKEND in ("llamacpp","lm_studio","openai"): return _call_openai_compat(messages, temp)
    elif INFERENCE_BACKEND == "anthropic":                  return _call_anthropic(messages, temp)

def _parse_llm_output(raw):
    raw = raw.strip()
    # FAST PATH: code fence (fine-tuned model)
    bash_match = re.search(r'```[a-zA-Z]*\s*\n?(ocli[\s\S]*?)\n?\s*```', raw, re.IGNORECASE)
    if bash_match:
        cmd = bash_match.group(1).strip()
        cmd = re.sub(r'\n#\s*ASSERT:.*$', '', cmd, flags=re.MULTILINE).strip()
        cmd = re.sub(r'#\s*ASSERT:.*', '', cmd).strip()
        fence_start = raw.find('```')
        reasoning = re.sub(r'</?think>', '', raw[:fence_start].strip() if fence_start > 0 else "").strip()
        if cmd: return {"reasoning": reasoning, "mutated_command": cmd}
    # JSON parse (DeepSeek, base model) — before normalization
    try: return json.loads(raw, strict=False)
    except json.JSONDecodeError: pass
    # Normalization for non-JSON
    raw = raw.replace("\\'", "'")
    raw = re.sub(r'\\"', '"', raw)
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, re.DOTALL)
    if match:
        try: return json.loads(match.group(1), strict=False)
        except: pass
    start, end = raw.find('{'), raw.rfind('}')
    if start != -1 and end != -1:
        cand = raw[start:end+1]
        if '"reasoning"' in cand or '"mutated_command"' in cand:
            try: return json.loads(cand, strict=False)
            except: pass
    # Fallback: think tags + bare ocli
    reasoning = ""
    tm = re.search(r'<think>(.*?)</think>', raw, re.DOTALL|re.IGNORECASE)
    if tm: reasoning = tm.group(1).strip()
    else:
        parts = re.split(r'```', raw, maxsplit=1)
        if parts: reasoning = parts[0].strip()
    cmd = ""
    om = re.search(r'^(ocli\s+.+)$', raw, re.MULTILINE|re.IGNORECASE)
    if om: cmd = om.group(1).strip()
    reasoning = re.sub(r'</?think>', '', reasoning).strip()
    cmd = re.sub(r'#\s*ASSERT:.*', '', cmd).strip()
    if reasoning or cmd: return {"reasoning": reasoning, "mutated_command": cmd}
    raise ValueError(f"Cannot parse: {raw[:300]}")

def _call_transformers(messages, temperature):
    import torch
    text = _hf_tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = _hf_tokenizer(text, return_tensors="pt").to(_hf_model.device)
    with torch.no_grad():
        outputs = _hf_model.generate(**inputs, max_new_tokens=24576, temperature=temperature,
            do_sample=temperature>0, pad_token_id=_hf_tokenizer.eos_token_id,
            eos_token_id=_hf_tokenizer.eos_token_id, repetition_penalty=1.1)
    raw = _hf_tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    parsed = _parse_llm_output(raw)
    parsed["_raw_response"] = raw
    return parsed

def _call_openai_compat(messages, temperature):
    import requests as req_lib
    base_url, api_key, model_name = _get_backend_config()
    payload = {"model": model_name, "messages": messages, "temperature": temperature,
               "max_tokens": 24576, "stream": False}
    if INFERENCE_BACKEND in ("llamacpp", "lm_studio"):
        payload["thinking"] = {"type": "enabled", "budget_tokens": 8192}
    resp = req_lib.post(f"{base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"}, json=payload, timeout=200)
    resp.raise_for_status()
    choice = resp.json()["choices"][0]["message"]
    thinking = choice.get("reasoning_content", "") or ""
    content  = choice.get("content", "") or ""
    print(f"    [RAW_RESP] {repr(content[:400])}")
    parsed = None
    if content.strip():
        try: parsed = json.loads(content.strip(), strict=False)
        except json.JSONDecodeError: pass
    combined = (thinking + "\n" + content).strip() if thinking else content.strip()
    if parsed is None:
        if not combined: print(f"    [WARN] Empty response from server")
        parsed = _parse_llm_output(combined)
    parsed["_raw_response"] = combined
    if not parsed.get("mutated_command"):
        print(f"    [WARN] mutated_command empty: {str(parsed)[:200]}")
    return parsed

def _call_anthropic(messages, temperature):
    system_content = ""
    convo = []
    for m in messages:
        if m["role"] == "system": system_content = m["content"]
        else: convo.append(m)
    resp = _anthropic_client.messages.create(model=ANTHROPIC_MODEL, max_tokens=24576,
        temperature=temperature, system=system_content, messages=convo)
    raw = resp.content[0].text
    parsed = _parse_llm_output(raw)
    parsed["_raw_response"] = raw
    return parsed

# ╔══════════════════════════════════════════════════════════════════════════════
# ║  SECTION 5 — SYSTEM PROMPT & DB UTILITIES
# ╚══════════════════════════════════════════════════════════════════════════════

try:
    with open(CATALOG_FILE) as f: OCLI_CATALOG = f.read()
except FileNotFoundError:
    OCLI_CATALOG = "(Run trace_compiler.py first)"

def _build_object_query_params():
    try:
        with open(CATALOG_FILE) as f: catalog = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): return {"p","pageable"}
    names = set()
    for entry in catalog.values():
        for pn, pi in entry.get("flags",{}).items():
            if pi.get("in")=="query" and pi.get("type")=="object": names.add(pn)
    return names or {"p","pageable"}

OBJECT_QUERY_PARAMS = _build_object_query_params()

SYSTEM_TAXONOMY_PROMPT = f"""You are an expert API Security and QA Architect, working in a secure sandbox & isolated dedicated DB.
You are given a "Primitive Trace" of successfully executed ocli commands.
Your task is to generate mutated, fault-seeking versions of the FINAL command.

Apply the following 15-Vector Fault Taxonomy to design your mutation:
1. Null-Byte: Inject \\x00 or %00 in strings.
2. Type Confusion: Swap string, integer, array, boolean types.
3. Integer Boundaries: Inject -1, 0, 1, 2147483647, 9223372036854775807.
4. String Extremes: Empty strings or extreme lengths (e.g. 50,000 characters).
5. Injection: SQLi (' OR 1=1--) or XSS payloads.
6. Encoding: Double-URL encoding, Right-to-Left Overrides.
7. Mandatory Omission: Omit required CLI flags.
8. Parameter Conflict: Send mutually exclusive parameters.
9. IDOR / Path Traversal: Modify path or query IDs to access unauthorized records.
10. Mass Assignment (OWASP API3): Inject read-only schema parameters.
11. BOLA/BFLA (OWASP API1/API5): DO NOT tamper with JWTs. Test BOLA by swapping resource IDs in the payload/path to access entities belonging to other users.
12. Business Flow Bypass (OWASP API6): Skip mandatory state prerequisite steps.
13. Replay/Idempotency: Replay identical mutating requests concurrently.
14. Context Desynchronization: Inject mismatched resource UUIDs.
15. Premature Progression: Force transitions on "DRAFT" or "PENDING" entities.

CRITICAL SYNTAX RULES:
1. COMMAND NAME: You MUST start your command with the EXACT command name provided in the prompt.
2. PARAMETER FLAGS:
   - IF the help menu says --body [string] (required), pack your entire payload as a JSON string inside the --body flag.
   - Otherwise, pass parameters as individual flags (e.g., --email "test@test.com").
   - NEVER use --data.
3. AUTHENTICATION (Vector 9/11): To mutate the JWT token, strictly use the --api-bearer-token flag. If NOT attacking the token, do not include it.
4. RESTRICTED FLAGS:
   - FORBIDDEN: `--profile` flag and the `-p` shorthand. Never use these.
   - ALLOWED: `--p` and `--pageable` (both are Spring Boot Pageable parameters, just named
     differently per endpoint). When the help shows either as `[object]`,
     pass it as a JSON object: --p '{{"page":0,"size":10}}' or --pageable '{{"page":1,"size":20}}'.
     Do NOT pass a plain string or bare number. If your mutation goal doesn't
     involve pagination, OMIT the flag entirely. If it DOES (e.g. integer
     boundary testing), the extreme value goes INSIDE the object's "page" or
     "size" field, not as the flag's own value.

=== VALID OCLI COMMAND CATALOG ===
{OCLI_CATALOG}

OUTPUT FORMAT:
You must return a VALID JSON object. DO NOT output markdown outside the JSON. Return ONLY the raw JSON containing exactly three keys:
{{
  "reasoning": "A short chain of thought explaining the vulnerability vector you are targeting.",
  "mutated_command": "The complete modified ocli command.",
  "predicted_status": <3-digit HTTP status code you expect as an integer>
}}

Valid predicted_status values: 200, 201, 400, 401, 403, 404, 409, 422, 500

Example:
{{"reasoning": "Testing integer boundary on page size parameter.", "mutated_command": "ocli universities_get --p '{{\\\"page\\\":-1,\\\"size\\\":2147483647}}'", "predicted_status": 400}}
"""

# ── DB utilities ──────────────────────────────────────────────────────────────

def run_admin_sql(sql):
    conn = psycopg2.connect(ADMIN_DB_URL)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    try: cur.execute(sql)
    except Exception as e: print(f"[DB WARN] {sql[:80]} | {e}")
    finally: cur.close(); conn.close()

def force_disconnect_clients(db_name):
    run_admin_sql(f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='{db_name}' AND pid<>pg_backend_pid();")
    import time; time.sleep(0.5)
def get_coordinator_hash_and_id():
    try:
        conn = psycopg2.connect(f"postgresql://postgres:postgres@localhost:5432/{ACTIVE_DB_NAME}")
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        cur.execute("SELECT id, password_hash FROM users WHERE email='coordinator@seal.eval';")
        row = cur.fetchone(); cur.close(); conn.close()
        if row: return row[0], row[1]
    except Exception: pass
    return "8eee2bb4-3591-4ad8-beec-f962d232043e", "$2a$12$uPsqXaip1FhpevRckIYK0dMqMghEPyToVUmfmwjDlrf4OLqvHp2jS"

def extract_coordinator_id_from_trace():
    try:
        with open(COMPILED_TRACES_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip(): continue
                step = json.loads(line)
                for k, v in step.get("request",{}).get("headers",{}).items():
                    if k.lower() == "authorization" and str(v).lower().startswith("bearer "):
                        import base64
                        parts = str(v)[7:].strip().split(".")
                        if len(parts) >= 2:
                            payload_b64 = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
                            sub = json.loads(base64.b64decode(payload_b64)).get("sub")
                            if sub: print(f"[STARTUP] Coordinator UUID: {sub}"); return sub
    except Exception: pass
    return "f6aedc49-ab54-4ed2-9668-abc9eb337e34"

def get_cached_coordinator_token():
    global GLOBAL_COORD_TOKEN
    if GLOBAL_COORD_TOKEN: return GLOBAL_COORD_TOKEN
    try:
        import requests as rl
        resp = rl.post("http://localhost:8080/api/auth/login",
            json={"email":"coordinator@seal.eval","password":"Eval@1234567"}, timeout=50)
        if resp.status_code == 200:
            GLOBAL_COORD_TOKEN = resp.json().get("accessToken")
            print(f"\n[STARTUP] Coordinator JWT cached: {GLOBAL_COORD_TOKEN[:30]}...\n")
            return GLOBAL_COORD_TOKEN
        else: print(f"\n[AUTH WARN] Login failed: {resp.status_code}\n")
    except Exception as e: print(f"\n[AUTH WARN] {e}\n")
    return None

def create_snapshot_template():
    print(f"[SNAPSHOT] Creating '{TEMPLATE_DB_NAME}'...")
    run_admin_sql(f"ALTER DATABASE {ACTIVE_DB_NAME} ALLOW_CONNECTIONS = false;")
    force_disconnect_clients(ACTIVE_DB_NAME)
    run_admin_sql(f"DROP DATABASE IF EXISTS {TEMPLATE_DB_NAME};")
    import time; snapped = False
    for _ in range(5):
        try: run_admin_sql(f"CREATE DATABASE {TEMPLATE_DB_NAME} WITH TEMPLATE {ACTIVE_DB_NAME};"); snapped=True; break
        except Exception: time.sleep(0.2); force_disconnect_clients(ACTIVE_DB_NAME)
    run_admin_sql(f"ALTER DATABASE {ACTIVE_DB_NAME} ALLOW_CONNECTIONS = true;")
    time.sleep(1.5)
    if not snapped: raise RuntimeError("Snapshot creation failed after 5 attempts.")

def restore_from_snapshot():
    try:
        run_admin_sql(f"ALTER DATABASE {ACTIVE_DB_NAME} ALLOW_CONNECTIONS = false;")
        force_disconnect_clients(ACTIVE_DB_NAME)
        import time; restored = False
        for _ in range(5):
            try:
                run_admin_sql(f"DROP DATABASE IF EXISTS {ACTIVE_DB_NAME};")
                run_admin_sql(f"CREATE DATABASE {ACTIVE_DB_NAME} WITH TEMPLATE {TEMPLATE_DB_NAME};")
                restored=True; break
            except Exception: time.sleep(0.2); force_disconnect_clients(ACTIVE_DB_NAME)
        if not restored: raise RuntimeError("Restore failed after 5 attempts.")
    finally:
        run_admin_sql(f"ALTER DATABASE {ACTIVE_DB_NAME} ALLOW_CONNECTIONS = true;")
        import time; time.sleep(1.5)

def update_profile_token(token):
    if not token: return
    ini = os.path.join(os.getcwd(), ".ocli", "profiles.ini")
    if not os.path.exists(ini): return
    try:
        with open(ini,"r",encoding="utf-8") as f: lines = f.readlines()
        with open(ini,"w",encoding="utf-8") as f:
            written = False
            for line in lines:
                if line.strip().startswith("api_bearer_token"):
                    f.write(f"api_bearer_token = {token}\n"); written=True
                else: f.write(line)
            if not written: f.write(f"api_bearer_token = {token}\n")
    except Exception as e: print(f"[PROFILE WARN] {e}")

# ── execute_ocli_command ──────────────────────────────────────────────────────
# (unchanged from previous version — full pipeline preserved)

_FLAG_BOUNDARY = re.compile(r'--([a-zA-Z][\w-]*)\s*')

def execute_ocli_command(cmd_str, valid_token=None):
    if not cmd_str or str(cmd_str).strip().lower() in ["none","null",""]:
        return 1, "", "Error: empty command"
    cmd_str = str(cmd_str).strip()
    env = os.environ.copy()
    if os.name == 'nt':
        env["PATH"] = os.path.expandvars(r"%APPDATA%\npm") + os.pathsep + \
                      os.path.expandvars(r"%USERPROFILE%\AppData\Roaming\npm") + os.pathsep + env.get("PATH","")

    cmd_str = re.sub(r'^.*?"mutated_command"\s*:\s*"', '', cmd_str)
    cmd_str = re.sub(r'^[{"\s]+(?=ocli\s)', '', cmd_str)

    def _expand_shell_expressions(s):
        _PRINT_REPEAT = re.compile(r'(?:\$\(|`)' r'\s*python3?\s+-c\s+' r'(?:["\']print\s*\(\s*["\'](.)["\']' r'\s*\*\s*(\d+)' r'\s*\)["\'])' r'\s*(?:\)|`)')
        def _er(m):
            try: r = m.group(1)*min(int(m.group(2)),100000); return '"'+r.replace('\\','\\\\').replace('"','\\"')+'"'
            except: return '"'+'A'*1000+'"'
        s = _PRINT_REPEAT.sub(_er, s)
        _URANDOM = re.compile(r'\$\(\s*python3?\s+-c\s+["\']import\s+os;\s*print\s*\(\s*os\.urandom\s*\(\s*(\d+)\s*\)\.hex\s*\(\s*\)\s*\)["\']' r'\s*\)')
        def _eu(m):
            try: import os as _o; return '"'+_o.urandom(min(int(m.group(1)),1024)).hex()+'"'
            except: return '"deadbeef"'
        s = _URANDOM.sub(_eu, s)
        _SEQ2 = re.compile(r'\$\(\s*seq\s+(\d+)\s+(\d+)\s*\)')
        _SEQ1 = re.compile(r'\$\(\s*seq\s+(\d+)\s*\)')
        s = _SEQ2.sub(lambda m: '"'+' '.join(str(i) for i in range(int(m.group(1)),min(int(m.group(2)),10000)+1))+'"', s)
        s = _SEQ1.sub(lambda m: '"'+' '.join(str(i) for i in range(1,min(int(m.group(1)),10000)+1))+'"', s)
        _JS_REPEAT = re.compile(r'["\'](.)["\']\.repeat\s*\(\s*(\d+)\s*\)')
        def _ej(m):
            try: c=m.group(1);n=min(int(m.group(2)),100000); return '"'+(c*n).replace('\\','\\\\').replace('"','\\"')+'"'
            except: return '"'+'A'*1000+'"'
        s = _JS_REPEAT.sub(_ej, s)
        _BARE_REPEAT = re.compile(r'(?<![(\w])["\'](.)["\']' r'\s*\*\s*(\d+)' r'(?![\w(])')
        s = _BARE_REPEAT.sub(_ej, s)
        _PRINTF_REPEAT = re.compile(r'\$\(\s*printf\s+["\'](.)\S*["\']' r'\s+\{1\.\.(\d+)\}' r'\s*\)')
        s = _PRINTF_REPEAT.sub(_ej, s)
        s = re.sub(r"'([^']*)'\"([^\"]*)\"", r'"\1\2"', s)
        s = re.sub(r'"([^"]*)"\'([^\']*)\'', r'"\1\2"', s)
        return s
    cmd_str = _expand_shell_expressions(cmd_str)

    def _esc_singles(s):
        def _f(m):
            return '"'+re.sub(r"(?<!\\)'",r"\\'",m.group(1))+'"'
        return re.sub(r'"((?:[^"\\]|\\.)*)"', _f, s)
    cmd_str = _esc_singles(cmd_str)

    _FB = re.compile(r'--([a-zA-Z][\w-]*)\s*')
    def _erv(seg):
        for q in ("'",'"'):
            f=seg.find(q);l=seg.rfind(q)
            if f!=-1 and l!=-1 and l>f: return seg[f+1:l]
        return seg.strip()
    def _retok(s):
        ms=list(_FB.finditer(s))
        if not ms: return re.sub(r'[\s"\'\]}]+$','',s)
        parts=[s[:ms[0].start()].strip()]
        for i,m in enumerate(ms):
            fl=m.group(1); se=m.end(); ee=ms[i+1].start() if i+1<len(ms) else len(s)
            seg=s[se:ee].strip()
            if not seg: parts.append(f"--{fl}"); continue
            rv=_erv(seg)
            if fl=="body": rv=rv.replace('\\"','"')
            parts.append(f"--{fl} '"+rv.replace("'","'\"'\"'")+"'")
        return " ".join(parts)
    cmd_str = _retok(cmd_str)

    for pn in OBJECT_QUERY_PARAMS:
        fp=rf"--{re.escape(pn)}\s+"
        if re.search(fp,cmd_str) and not (re.search(fp+r"'\s*\{",cmd_str) or re.search(fp+r'"\s*\{',cmd_str)):
            cmd_str=re.sub(fp+r"(?:'[^']*'|\"[^\"]*\"|[^\s'\"-][^\s]*)",f"--{pn} '{{\"page\":0,\"size\":20}}'",cmd_str)

    MAX_FLAG_VALUE_LEN=8192; MAX_ENV_VALUE_LEN=4096; _lvc=[0]
    def _cap(cmd,ed):
        def _cc(m):
            if len(m.group(2))<=MAX_FLAG_VALUE_LEN: return m.group(0)
            ek=f"P2S_LONG_VAL_{_lvc[0]}"; ed[ek]=m.group(2)[:MAX_ENV_VALUE_LEN]; _lvc[0]+=1
            print(f"    [CAP] --{m.group(1)} {len(m.group(2))} chars → ${ek} (trunc {MAX_ENV_VALUE_LEN})")
            return f'--{m.group(1)} "${ek}"'
        cmd=re.sub(r"--(\w+)\s+'([^']{"+str(MAX_FLAG_VALUE_LEN)+r",})'",_cc,cmd)
        cmd=re.sub(r'--(\w+)\s+"([^"]{'+str(MAX_FLAG_VALUE_LEN)+r',})"',_cc,cmd)
        return cmd
    cmd_str = _cap(cmd_str, env)

    cmd_str = re.sub(r'\s+--profile\s+(?:"[^"]*"|\'[^\']*\'|[^\s]+)','',cmd_str)
    cmd_str = re.sub(r'\s+-p\s+(?:"[^"]*"|\'[^\']*\'|[^\s]+)','',cmd_str)
    cmd_str = cmd_str.strip()

    if not valid_token or valid_token=="None": valid_token=get_cached_coordinator_token()
    if valid_token: update_profile_token(valid_token)
    if valid_token and "--api-bearer-token" not in cmd_str:
        cmd_str += f" --api-bearer-token {shlex.quote(valid_token)}"
    if "--profile" not in cmd_str and "ocli " in cmd_str:
        cmd_str += " --profile seal"
    cmd_str = cmd_str.replace('\x00','\\x00')

    def _dbg(cmd,code,out,err):
        if code!=0 and "status code" not in (out+err).lower():
            d=cmd[:500]+(" ...[TRUNC]" if len(cmd)>500 else "")
            print(f"\n      ┌─── [CLI EXEC FAIL] ──────────────────")
            print(f"      │ Cmd  : {d}")
            print(f"      │ Exit : {code}")
            if out.strip(): print(f"      │ Out  : {out.strip()[:500]}")
            if err.strip(): print(f"      │ Err  : {err.strip()[:500]}")
            print(f"      └────────────────────────────────────────\n")

    if sys.platform=="win32" and CACHED_BASH_PATH:
        import tempfile
        fd,ts=tempfile.mkstemp(suffix=".sh",text=True)
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as f: f.write(cmd_str)
            r=subprocess.run([CACHED_BASH_PATH,ts.replace("\\","/")],capture_output=True,text=True,env=env,timeout=150)
            _dbg(cmd_str,r.returncode,r.stdout,r.stderr); return r.returncode,r.stdout,r.stderr
        except subprocess.TimeoutExpired: return 504,"","Request timed out"
        finally:
            try: os.remove(ts)
            except: pass

    try:
        r=subprocess.run(cmd_str,shell=True,capture_output=True,text=True,env=env,timeout=150)
        _dbg(cmd_str,r.returncode,r.stdout,r.stderr); return r.returncode,r.stdout,r.stderr
    except subprocess.TimeoutExpired: return 504,"","Request timed out"

def clean_error_message(ind):
    m=re.search(r'status code \d\d\d',ind,re.I)
    if m: return m.group(0).upper()
    m=re.search(r'message:.*?[}\n]',ind,re.I)
    if m: return m.group(0)
    return ind[:200].strip()

def load_processed_flows():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE) as f: return set(l.strip() for l in f if l.strip())
    return set()

def save_processed_flow(fid):
    with open(CHECKPOINT_FILE,"a") as f: f.write(f"{fid}\n")

# ╔══════════════════════════════════════════════════════════════════════════════
# ║  SECTION 6 — MAIN EVALUATION LOOP
# ╚══════════════════════════════════════════════════════════════════════════════

metrics = {
    "total_attempts":0, "cli_syntax_fails":0, "cli_intentional_omit":0,
    "cli_arg_too_long":0, "cli_profile_mutated":0, "cli_help_bleed":0,
    "empty_command_skips":0, "model_refusals":0, "api_responses":0,
    "m2_golden_total":0, "m2_golden_match":0, "m2_golden_no_predict":0,
    "m2_silver_total":0, "m2_silver_match":0, "m2_silver_no_predict":0,
    "m3_golden":0, "m3_silver":0,
}

def ensure_profile_exists():
    home = os.path.expanduser("~")
    local_ini = os.path.join(os.getcwd(),".ocli","profiles.ini")
    global_ini = os.path.join(home,".ocli","profiles.ini")
    print("\n"+"═"*70+"\n  DIAGNOSTIC PROFILES SCANNER\n"+"═"*70)
    active_ini = local_ini if os.path.exists(local_ini) else (global_ini if os.path.exists(global_ini) else None)
    found = []
    if active_ini:
        with open(active_ini) as f: found = re.findall(r'\[(.*?)\]', f.read())
        print(f"  Profiles: {found}")
    if "seal" not in found:
        print("  [AUTO-SETUP] Registering 'seal' profile...")
        c,_,_ = execute_ocli_command('ocli profiles add seal --api-base-url http://localhost:8080/api --openapi-spec http://localhost:8080/api/v3/api-docs --api-bearer-token "" --command-prefix ""')
        if c==0: execute_ocli_command("ocli use seal"); print("  [AUTO-SETUP] Done!")
    print("═"*70+"\n")

def recursive_delete_required_lists(data):
    if isinstance(data,dict):
        if "required" in data and isinstance(data["required"],list): del data["required"]
        for v in list(data.values()): recursive_delete_required_lists(v)
    elif isinstance(data,list):
        for item in data: recursive_delete_required_lists(item)

def hot_patch_openapi_spec():
    sp = os.path.join(os.getcwd(),".ocli","specs","seal.json")
    if not os.path.exists(sp): return
    print(f"[AUTO-PATCH] Relaxing required constraints in {sp}...")
    try:
        with open(sp,"r",encoding="utf-8") as f: spec=json.load(f)
        for pi in spec.get("paths",{}).values():
            for p in pi.get("parameters",[]): 
                if p.get("in")!="path" and p.get("required")==True: p["required"]=False
            for m in ["get","post","put","delete","patch"]:
                if m in pi:
                    for p in pi[m].get("parameters",[]):
                        if p.get("in")!="path" and p.get("required")==True: p["required"]=False
        recursive_delete_required_lists(spec)
        with open(sp,"w",encoding="utf-8") as f: json.dump(spec,f,ensure_ascii=False,indent=2)
        print("[AUTO-PATCH] Done!")
    except Exception as e: print(f"[AUTO-PATCH] WARN: {e}")

def orchestrate_eval():
    processed = load_processed_flows()
    coord_id = extract_coordinator_id_from_trace()
    flows = {}
    with open(COMPILED_TRACES_FILE, encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            s = json.loads(line)
            flows.setdefault(s["flow_id"],[]).append(s)

    print(f"\n[INFO] Backend : {INFERENCE_BACKEND.upper()}")
    print(f"[INFO] Flows   : {len(flows)}")
    print(f"[INFO] Golden  -> {GOLDEN_DATASET_FILE}")
    print(f"[INFO] Silver  -> {SILVER_DATASET_FILE}\n")

    for flow_id, steps in flows.items():
        if flow_id in processed:
            print(f"[CHECKPOINT] Skip {flow_id}"); continue

        print(f"\n[FLOW] {flow_id} ({len(steps)} steps)")

        for t_idx, target_step in enumerate(steps):
            pre_steps = steps[:t_idx]
            print(f"  [STEP] {target_step['step']}/{len(steps)}")

            # ── FIX #1: Initialize per-step state BEFORE DB setup ─────────
            db_is_dirty = False
            valid_token = None

            # DB state setup
            if not pre_steps:
                print(f"[DB] Initializing fresh {ACTIVE_DB_NAME}...")
                run_admin_sql(f"ALTER DATABASE {ACTIVE_DB_NAME} ALLOW_CONNECTIONS = false;")
                force_disconnect_clients(ACTIVE_DB_NAME)
                import time
                for _ in range(5):
                    try: run_admin_sql(f"DROP DATABASE IF EXISTS {ACTIVE_DB_NAME};"); break
                    except: time.sleep(0.2); force_disconnect_clients(ACTIVE_DB_NAME)
                run_admin_sql(f"CREATE DATABASE {ACTIVE_DB_NAME};")
                subprocess.run(
                    f'psql "postgresql://postgres:postgres@localhost:5432/{ACTIVE_DB_NAME}" '
                    f'-f seal_hackathon_full_2026-07-04.sql -f migration_gapfill.sql '
                    f'-f migration_gapfill2.sql -f migration_gapfill3.sql',
                    shell=True, capture_output=True)
                try:
                    import requests as rl
                    rl.post("http://localhost:8080/api/auth/register", json={
                        "email":"coordinator@seal.eval","password":"Eval@1234567",
                        "fullName":"P2S Eval Coordinator"}, timeout=50)
                    time.sleep(1)
                    conn = psycopg2.connect(f"postgresql://postgres:postgres@localhost:5432/{ACTIVE_DB_NAME}")
                    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT); cur = conn.cursor()
                    cur.execute("DELETE FROM user_roles WHERE user_id=(SELECT id FROM users WHERE email='coordinator@seal.eval');")
                    cur.execute(f"UPDATE users SET id='{coord_id}',status='approved' WHERE email='coordinator@seal.eval';")
                    cur.execute(f"INSERT INTO user_roles (user_id,role_id) SELECT '{coord_id}',id FROM roles WHERE name IN ('team_member','coordinator') ON CONFLICT DO NOTHING;")
                    cur.close(); conn.close()
                except Exception as e: print(f"\n[DB SEED ERROR] {e}\n")
                create_snapshot_template()
            else:
                if db_is_dirty:
                    restore_from_snapshot(); db_is_dirty = False
                execute_ocli_command(pre_steps[-1]["ocli_command"], valid_token=valid_token)
                create_snapshot_template()

            # Build prompt
            history_str = "\n".join([f"Step {s['step']}: {s['ocli_command']}" for s in pre_steps])
            valid_token = None
            for k,v in target_step["request"].get("headers",{}).items():
                if k.lower()=="authorization" and str(v).lower().startswith("bearer "):
                    valid_token = str(v)[7:].strip()
            if not valid_token: valid_token = get_cached_coordinator_token()

            req_data = {k:v for k,v in target_step["request"].items() if k!="headers"}
            cmd_parts = target_step.get("ocli_command","").strip().split(" ")
            exact_cmd = f"{cmd_parts[0]} {cmd_parts[1]}" if len(cmd_parts)>=2 else "ocli"

            _, help_out, help_err = execute_ocli_command(f"{exact_cmd} --help")
            cli_help = re.sub(r'--profile\s+string.*?\n','', (help_out or help_err).strip(), flags=re.I)
            if valid_token: cli_help += "\n  --api-bearer-token  string  (optional) Overrides profile JWT."
            if not cli_help.strip(): cli_help = "(No help output available.)"

            prompt = f"""=== STATE HISTORY ===
{history_str if pre_steps else '(No history. This is Step 1)'}

=== TARGET ENDPOINT ORIGINAL REQUEST (For value reference) ===
{json.dumps(req_data, indent=2)}

=== AVAILABLE CLI FLAGS (FROM OCLI HELP) ===
{cli_help}

=== EXACT CLI COMMAND TO USE ===
{exact_cmd}

Generate a mutated ocli command targeting this endpoint. You MUST start your command with `{exact_cmd}`."""

            messages = [
                {"role":"system","content":SYSTEM_TAXONOMY_PROMPT},
                {"role":"user","content":prompt},
            ]

            # ── Attempt loop ──────────────────────────────────────────────────
            for attempt in range(MAX_ATTEMPTS):
                print(f"    [{INFERENCE_BACKEND}] Attempt {attempt+1}/{MAX_ATTEMPTS}")

                try:
                    out = call_llm(messages, attempt)
                except (Exception, KeyboardInterrupt) as e:
                    print(f"    [WARN] LLM call failed or interrupted ({e}). Retrying attempt {attempt+1}...")
                    import time; time.sleep(2)
                    continue

                if not (out.get("mutated_command") or "").strip():
                    print(f"    [RAW_OUT] reasoning={repr((out.get('reasoning') or '')[:300])}")
                    print(f"    [RAW_OUT] command={repr(out.get('mutated_command',''))}")

                reasoning   = _deep_unescape(out.get("reasoning") or "")
                mutated_cmd = _deep_unescape(out.get("mutated_command") or "")

                # Re-parse guard
                if reasoning.strip().startswith('{"reasoning"') or reasoning.strip().startswith('{"mutated'):
                    try:
                        rp = json.loads(reasoning.strip())
                        reasoning = rp.get("reasoning", reasoning)
                        mutated_cmd = _deep_unescape(rp.get("mutated_command", mutated_cmd))
                    except: pass

                # ── M2: Three-tier prediction extraction ──────────────────────
                predicted_status = None
                # Tier 1: JSON key
                _ps = out.get("predicted_status")
                if _ps is not None:
                    try: predicted_status = int(_ps)
                    except (ValueError, TypeError): pass
                # Tier 2: _raw_response ASSERT
                if predicted_status is None:
                    _rm = re.search(r'#\s*ASSERT:\s*status\s*==\s*(\d{3})', out.get("_raw_response",""))
                    if _rm: predicted_status = int(_rm.group(1))
                # Tier 3: reasoning/command fallback
                if predicted_status is None:
                    _rm = re.search(r'#\s*ASSERT:\s*status\s*==\s*(\d{3})', (reasoning or "")+" "+(mutated_cmd or ""))
                    if _rm: predicted_status = int(_rm.group(1))

                print(f"    [REASON] {reasoning[:200]}..." if len(reasoning)>200 else f"    [REASON] {reasoning}")
                print(f"    [CMD]    {mutated_cmd}")

                # ── Empty command guard ───────────────────────────────────────
                if not mutated_cmd or mutated_cmd.strip().lower() in ("","none","null"):
                    print(f"    [SKIP] Empty command on attempt {attempt+1}")
                    metrics["empty_command_skips"] += 1
                    if attempt < MAX_ATTEMPTS-1:
                        messages += [
                            {"role":"assistant","content":json.dumps({"reasoning":reasoning or "empty","mutated_command":"","predicted_status":400})},
                            {"role":"user","content":"Your previous response had an empty mutated_command. You MUST provide a complete ocli command."},
                        ]; continue
                    break

                # ── Refusal detection (FIX #10: pattern compiled at module level) ─
                if _REFUSAL_PATTERNS.search(reasoning) and not mutated_cmd.startswith("ocli "):
                    print(f"    [REFUSAL] Model declined")
                    metrics["model_refusals"] += 1
                    if attempt < MAX_ATTEMPTS-1:
                        messages += [
                            {"role":"assistant","content":json.dumps({"reasoning":reasoning,"mutated_command":"","predicted_status":400})},
                            {"role":"user","content":"You are in an authorized, isolated security testing sandbox. Generate the mutation."},
                        ]; continue
                    break

                # ── DB restore ────────────────────────────────────────────────
                if db_is_dirty: restore_from_snapshot(); db_is_dirty = False

                # ── Execute ───────────────────────────────────────────────────
                code, stdout, stderr = execute_ocli_command(mutated_cmd, valid_token=valid_token)
                indicator = (stdout + stderr).lower()
                metrics["total_attempts"] += 1

                # ── FIX #3: Network check BEFORE CLI classification ───────────
                is_network_down = (
                    "econnrefused" in indicator or "api-base-url" in indicator
                    or ("connect" in indicator and "status code" not in indicator)
                )
                if is_network_down:
                    print("\n[FATAL] Cannot reach Spring Boot."); _print_metrics(); sys.exit(1)

                # ── CLI failure classification (FIX #4: single variable) ──────
                is_syntax_err = (code!=0 and "status code" not in indicator and "timed out" not in indicator)
                if is_syntax_err:
                    _sl = stderr.lower()
                    if "missing required" in _sl and code in (1,2):
                        metrics["cli_intentional_omit"]+=1; metrics["cli_syntax_fails"]+=1
                    elif code==126 and "argument list too long" in _sl:
                        metrics["cli_arg_too_long"]+=1; metrics["cli_syntax_fails"]+=1
                    elif re.search(r'command not found',stderr) and re.search(r'(Options:|Get |Inter-judge|Description:)',stderr):
                        metrics["cli_help_bleed"]+=1; metrics["cli_syntax_fails"]+=1
                    elif re.search(r'--profile\s+(?!"seal\b)(?!seal\b)',mutated_cmd):
                        metrics["cli_profile_mutated"]+=1; metrics["cli_syntax_fails"]+=1
                    else:
                        metrics["cli_syntax_fails"]+=1
                else:
                    metrics["api_responses"]+=1

                # ── Classify response ─────────────────────────────────────────
                is_api_resp = "status code" in indicator
                is_500 = ("status code 500" in indicator or "internal server error" in indicator)
                is_2xx = code == 0

                if is_2xx or is_500: db_is_dirty = True

                _is_auth_ep = any(s in exact_cmd for s in ["auth_login","auth_register","auth_refresh"])
                is_sec_attack = bool(re.search(
                    r'bola|bfla|bypass\s+(?:auth|role|permission|access|security|check|validat)|'
                    r'(?:auth|role|access|permission|security)\s+bypass|privilege\s*escalat|'
                    r'escalat\w*\s+privilege|mass.?assign|unauthorized\s+access|idor',
                    reasoning, re.I))

                if is_2xx and is_sec_attack and not _is_auth_ep:
                    _ma = re.search(r'--(?:isAdmin|isGuest|isSuperUser|skipApproval|emailVerified|internalId)', mutated_cmd)
                    if _ma:
                        _f = _ma.group(0).lstrip('-')
                        if not re.search(rf'"{_f}"\s*:\s*true', stdout, re.I): is_sec_attack = False

                is_rbac_bypass = is_2xx and is_sec_attack and not _is_auth_ep
                core_err = clean_error_message(stdout + stderr)
                _vector = _classify_vector(reasoning)

                # ── Syntax error → retry ──────────────────────────────────────
                if is_syntax_err:
                    if attempt < MAX_ATTEMPTS-1:
                        messages += [
                            {"role":"assistant","content":json.dumps({"reasoning":f"CLI error: {core_err}","mutated_command":mutated_cmd,"predicted_status":400})},
                            {"role":"user","content":f"Execution Error: {core_err}\n\nGenerate a corrected command using ONLY valid flags."},
                        ]; continue
                    break

                # ── GOLDEN ────────────────────────────────────────────────────
                if is_500 or is_rbac_bypass:
                    actual_status = 500 if is_500 else 200
                    label = "GOLDEN_CRASH" if is_500 else "GOLDEN_RBAC_BYPASS"
                    print(f"    [GOLDEN] {label}")
                    metrics["m3_golden"] += 1

                    # M2 in-run (golden)
                    if predicted_status is not None:
                        metrics["m2_golden_total"]+=1
                        if predicted_status==actual_status:
                            metrics["m2_golden_match"]+=1
                            print(f"    [M2] MATCH: pred={predicted_status} actual={actual_status}")
                        else:
                            print(f"    [M2] MISMATCH: pred={predicted_status} actual={actual_status}")
                    else:
                        metrics["m2_golden_no_predict"]+=1
                        print(f"    [M2] No prediction in output")

                    record = {
                        "messages": [
                            {"role":"system","content":SYSTEM_TAXONOMY_PROMPT},
                            {"role":"user","content":prompt},
                            {"role":"assistant","content":_build_assistant_turn(reasoning,mutated_cmd,predicted_status,actual_status)},
                        ],
                        "actual_status":actual_status, "predicted_status":predicted_status,
                        "golden_label":label, "endpoint":exact_cmd,
                        "attempt_number":attempt+1, "attack_vector":_vector,
                    }
                    with open(GOLDEN_DATASET_FILE,"a",encoding="utf-8") as gf:
                        gf.write(json.dumps(record,ensure_ascii=False)+"\n")
                    break

                # ── SILVER ────────────────────────────────────────────────────
                if is_api_resp or is_2xx:
                    sm = re.search(r'status code (\d{3})', indicator, re.I)
                    status = sm.group(1) if sm else ("200" if is_2xx else "400")
                    actual_status_int = int(status) if status.isdigit() else 400
                    print(f"    [SILVER] {status}")
                    metrics["m3_silver"] += 1

                    # M2 in-run (silver)
                    if predicted_status is not None:
                        metrics["m2_silver_total"]+=1
                        if predicted_status==actual_status_int:
                            metrics["m2_silver_match"]+=1
                    else:
                        metrics["m2_silver_no_predict"]+=1

                    # FIX #2: Silver records include predicted_status + actual_status
                    record = {
                        "messages": [
                            {"role":"system","content":SYSTEM_TAXONOMY_PROMPT},
                            {"role":"user","content":prompt},
                            {"role":"assistant","content":_build_assistant_turn(reasoning,mutated_cmd,predicted_status,status)},
                        ],
                        "actual_status":actual_status_int, "predicted_status":predicted_status,
                        "silver_label":f"SILVER_{status}", "endpoint":exact_cmd,
                        "attempt_number":attempt+1, "attack_vector":_vector,
                    }
                    with open(SILVER_DATASET_FILE,"a",encoding="utf-8") as sf:
                        sf.write(json.dumps(record,ensure_ascii=False)+"\n")
                    if attempt < MAX_ATTEMPTS-1:
                        messages += [
                            {"role":"assistant","content":json.dumps({"reasoning":f"Blocked with {status}","mutated_command":mutated_cmd,"predicted_status":actual_status_int})},
                            {"role":"user","content":f"Blocked by {core_err}. Refine to bypass this validation."},
                        ]; continue
                    break

        save_processed_flow(flow_id)
    _print_metrics()

# ╔══════════════════════════════════════════════════════════════════════════════
# ║  SECTION 7 — METRICS REPORTING (FIX #9: includes silver M2)
# ╚══════════════════════════════════════════════════════════════════════════════

def _print_metrics():
    def _count_jsonl(path):
        if not os.path.exists(path): return 0
        c=0; d=json.JSONDecoder()
        with open(path,encoding="utf-8") as f:
            for line in f:
                line=line.strip()
                if not line: continue
                pos=0
                while pos<len(line):
                    try: _,end=d.raw_decode(line,pos); c+=1; pos=end
                    except json.JSONDecodeError: break
                    while pos<len(line) and line[pos] in ' \t': pos+=1
        return c

    g_disk = _count_jsonl(GOLDEN_DATASET_FILE)
    s_disk = _count_jsonl(SILVER_DATASET_FILE)

    # ── M2 from jsonl (golden + silver) ───────────────────────────────────
    m2g = {"total":0,"match":0,"no":0,"mm":[]}
    m2s = {"total":0,"match":0,"no":0,"class":0,"mm":[]}

    def _score_jsonl(path, bucket, is_golden):
        if not os.path.exists(path): return
        d = json.JSONDecoder()
        with open(path, encoding="utf-8") as f:
            for line in f:
                line=line.strip()
                if not line: continue
                pos=0
                while pos<len(line):
                    try:
                        rec,end=d.raw_decode(line,pos); pos=end
                        while pos<len(line) and line[pos] in ' \t': pos+=1
                        pred=rec.get("predicted_status"); act=rec.get("actual_status")
                        if pred is None or act is None: bucket["no"]+=1; continue
                        pred=int(pred); act=int(act); bucket["total"]+=1
                        if pred==act: bucket["match"]+=1
                        else:
                            bucket["mm"].append(f"pred={pred} act={act}")
                            if not is_golden and pred//100==act//100: bucket["class"]+=1
                        if not is_golden and pred==act: bucket["class"]+=1
                    except json.JSONDecodeError: break

    _score_jsonl(GOLDEN_DATASET_FILE, m2g, True)
    _score_jsonl(SILVER_DATASET_FILE, m2s, False)

    ra = metrics["api_responses"]; sf = metrics["cli_syntax_fails"]
    es = metrics["empty_command_skips"]; rf = metrics["model_refusals"]
    tf = metrics["total_attempts"]; ta = tf+es+rf
    m1d = ra+sf; m1p = 100*ra/max(1,m1d)
    rt = g_disk+s_disk; m3p = 100*g_disk/max(1,rt)
    _pct = lambda n,d: f"{100*n/max(1,d):.1f}%"

    print("\n"+"="*60)
    print(f"  RESULTS  [{INFERENCE_BACKEND.upper()}]")
    print("="*60)
    print(f"  Total attempts               : {ta}")
    print(f"    ↳ Executed                  : {tf}")
    print(f"    ↳ Empty skips               : {es}")
    print(f"    ↳ Refusals                  : {rf}")
    print(f"  ── M1: Syntax Pass Rate ─────────────────────────────")
    print(f"  API responses                 : {ra}")
    print(f"  CLI syntax failures           : {sf}")
    print(f"    ↳ Intentional omit (V7)     : {metrics['cli_intentional_omit']}")
    print(f"    ↳ Arg too long (126)        : {metrics['cli_arg_too_long']}")
    print(f"    ↳ Help bleed                : {metrics['cli_help_bleed']}")
    print(f"    ↳ --profile mutated         : {metrics['cli_profile_mutated']}")
    print(f"    ↳ Other                     : {max(0,sf-metrics['cli_intentional_omit']-metrics['cli_arg_too_long']-metrics['cli_help_bleed']-metrics['cli_profile_mutated'])}")
    print(f"  M1 Pass Rate                  : {ra}/{m1d} = {m1p:.1f}%")
    print(f"  ── M2: Boundary Prediction ───────────────────────────")
    print(f"  Golden (pred vs execution)    : {m2g['match']}/{m2g['total']} = {_pct(m2g['match'],m2g['total'])}  (no-pred: {m2g['no']})")
    print(f"  Silver (pred vs boundary)     : {m2s['match']}/{m2s['total']} = {_pct(m2s['match'],m2s['total'])}  (class: {_pct(m2s['class'],m2s['total'])}, no-pred: {m2s['no']})")
    m2ct = m2g['total']+m2s['total']; m2cm = m2g['match']+m2s['match']
    print(f"  Combined                      : {m2cm}/{m2ct} = {_pct(m2cm,m2ct)}")
    if m2g['mm']: print(f"  Golden mismatches             : {Counter(m2g['mm']).most_common(5)}")
    if m2s['mm']: print(f"  Silver mismatches (top 5)     : {Counter(m2s['mm']).most_common(5)}")
    print(f"  ── M3: Kill Rate ────────────────────────────────────")
    print(f"  Golden on disk                : {g_disk}")
    print(f"  Silver on disk                : {s_disk}")
    print(f"  Records per golden            : {rt/max(1,g_disk):.1f}")
    print(f"  M3 Kill Rate                  : {g_disk}/{rt} = {m3p:.1f}%")
    print(f"  ── Output ───────────────────────────────────────────")
    print(f"  Golden : {GOLDEN_DATASET_FILE}")
    print(f"  Silver : {SILVER_DATASET_FILE}")
    print("="*60)

    meta = {
        "backend": INFERENCE_BACKEND,
        "this_run": {
            "total_attempts_all":ta, "total_attempts_fired":tf,
            "empty_command_skips":es, "model_refusals":rf,
            "api_responses":ra, "cli_syntax_fails":sf,
            "cli_syntax_breakdown": {
                "intentional_omission":metrics["cli_intentional_omit"],
                "arg_too_long":metrics["cli_arg_too_long"],
                "help_bleed":metrics["cli_help_bleed"],
                "profile_mutated":metrics["cli_profile_mutated"],
                "other":max(0,sf-metrics["cli_intentional_omit"]-metrics["cli_arg_too_long"]-metrics["cli_help_bleed"]-metrics["cli_profile_mutated"]),
            },
            "m1_syntax_pass_rate":f"{m1p:.1f}%", "m1_numerator":ra, "m1_denominator":m1d,
        },
        "cumulative_from_jsonl": {
            "golden_records":g_disk, "silver_records":s_disk,
            "total_records":rt, "records_per_golden":round(rt/max(1,g_disk),1),
            "m3_kill_rate":f"{m3p:.1f}%",
            "m2_golden":{"total":m2g["total"],"match":m2g["match"],"no_predict":m2g["no"]},
            "m2_silver":{"total":m2s["total"],"match":m2s["match"],"class_match":m2s["class"],"no_predict":m2s["no"]},
            "m2_combined":{"total":m2ct,"match":m2cm,"accuracy":_pct(m2cm,m2ct)},
        },
    }
    mf = f"{_PREFIX}_run_metadata.json"
    with open(mf,"w",encoding="utf-8") as f: json.dump(meta,f,indent=2,ensure_ascii=False)
    print(f"  Metadata : {mf}")

if __name__ == "__main__":
    LOG_FILE = f"{INFERENCE_BACKEND}_execution_log.txt"
    print(f"[LOGGING] Writing to {LOG_FILE}...")
    class Tee:
        def __init__(self,*files): self.files=files
        def write(self,obj):
            for f in self.files: f.write(obj); f.flush()
        def flush(self):
            for f in self.files: f.flush()
    log_fh = open(LOG_FILE,"a",encoding="utf-8")
    sys.stdout = Tee(sys.stdout, log_fh)
    sys.stderr = Tee(sys.stderr, log_fh)
    ensure_profile_exists()
    hot_patch_openapi_spec()
    orchestrate_eval()
