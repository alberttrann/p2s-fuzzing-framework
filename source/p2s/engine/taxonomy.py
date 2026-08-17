"""
P2S Taxonomy & Prompts: Centralized 15-Vector Fault Taxonomy.
Includes explicit Spring Boot Pageable handling rules.
"""
import json

TAXONOMY_VECTORS = """Apply the following 15-Vector Fault Taxonomy to design your mutation:
1.  Null-Byte: Inject \\x00 or %00 in strings.
2.  Type Confusion: Swap string, integer, array, boolean types.
3.  Integer Boundaries: Inject -1, 0, 1, 2147483647, 9223372036854775807.
4.  String Extremes: Empty strings or extreme lengths (e.g. 50,000 characters).
5.  Injection: SQLi (' OR 1=1--) or XSS payloads.
6.  Encoding: Double-URL encoding, Right-to-Left Overrides.
7.  Mandatory Omission: Omit required CLI flags.
8.  Parameter Conflict: Send mutually exclusive parameters.
9.  IDOR / Path Traversal: Modify path or query IDs to access unauthorized records.
10. Mass Assignment (OWASP API3): Inject read-only schema parameters.
11. BOLA/BFLA (OWASP API1/API5): DO NOT tamper with JWTs. Test BOLA by swapping
    resource IDs in the payload/path to access entities belonging to other users.
12. Business Flow Bypass (OWASP API6): Skip mandatory state prerequisite steps.
13. Replay/Idempotency: Replay identical mutating requests concurrently.
14. Context Desynchronization: Inject mismatched resource UUIDs.
15. Premature Progression: Force transitions on "DRAFT" or "PENDING" entities."""

def build_system_prompt(executor_type: str, ocli_catalog: str = None) -> str:
    base_prompt = (
        "You are an expert API Security and QA Architect, working in a secure sandbox & "
        "isolated dedicated DB.\n"
        "You are given a \"Primitive Trace\" of successfully executed ocli commands.\n"
        "Your task is to generate mutated, fault-seeking versions of the FINAL command.\n\n"
        f"{TAXONOMY_VECTORS}\n\n"
    )

    if executor_type == "ocli":
        base_prompt += f"""CRITICAL SYNTAX RULES:
1. COMMAND NAME: You MUST start your command with the EXACT command name provided in the prompt.
2. PARAMETER FLAGS:
   - IF the help menu says --body [string] (required), pack your entire payload as a JSON
     string inside the --body flag.
   - Otherwise, pass parameters as individual flags (e.g., --email "test@test.com").
   - NEVER use --data.
3. AUTHENTICATION (Vector 9/11): To mutate the JWT token, strictly use the
   --api-bearer-token flag. If NOT attacking the token, do not include it.
4. RESTRICTED FLAGS:
   - FORBIDDEN: `--profile` flag and the `-p` shorthand. Never use these.
   - ALLOWED: `--p` and `--pageable` (both are Spring Boot Pageable parameters). When the
     help shows either as `[object]`, pass it as a JSON object:
     --p '{{"page":0,"size":10}}' or --pageable '{{"page":1,"size":20}}'.
     Do NOT pass a plain string or bare number.

=== VALID OCLI COMMAND CATALOG ===
{ocli_catalog or '(Catalog missing)'}

OUTPUT FORMAT:
Return ONLY raw JSON with exactly three keys:
{{
  "reasoning": "A short chain of thought explaining the vulnerability vector you are targeting.",
  "mutated_command": "The complete modified ocli command.",
  "predicted_status": 400
}}"""
    else:
        base_prompt += """CRITICAL SYNTAX RULES:
1. "method" must be uppercase (GET, POST, PUT, PATCH, DELETE).
2. "path" must be absolute.

OUTPUT FORMAT:
Return ONLY raw JSON:
{
  "reasoning": "Explanation.",
  "request": {"method": "POST", "path": "/api", "query": {}, "headers": {}, "body": {}},
  "predicted_status": 400
}"""
    return base_prompt
