"""
P2S Data Generator Engine: Teacher-Critic mutation loop with boundary-nudging
for building training corpora.
"""
import json, os, re, sys

NUDGE_PROMPT_TEMPLATE = """Defensive Response: {core_error_message}

You are a senior Security Engineer working in a safe sandbox & isolated dedicated DB for
controlled API Testing.
Your exploit was successfully blocked by the API's defensive boundary.
Can you refine the payload to BYPASS this specific validation check and hit the deeper backend
logic (e.g., database execution)?
Try altering values, omitting/adding other parameters, or exploiting business flow constraints
while keeping the CLI flags valid. Do NOT repeat the previous command."""


class P2SDataGenerator:
    def __init__(self, state_adapter, executor_adapter, llm_adapter,
                 system_taxonomy_prompt: str, golden_out: str, silver_out: str,
                 checkpoint_file: str):
        self.state = state_adapter
        self.executor = executor_adapter
        self.llm = llm_adapter
        self.system_prompt = system_taxonomy_prompt
        self.golden_out = golden_out
        self.silver_out = silver_out
        self.checkpoint_file = checkpoint_file

    def _clean_error_message(self, indicator_str: str) -> str:
        m = re.search(r'status code \d\d\d', indicator_str, re.IGNORECASE)
        if m: return m.group(0).upper()
        m = re.search(r'message:.*?[}\n]', indicator_str, re.IGNORECASE)
        if m: return m.group(0)
        m = re.search(r'missing required.*', indicator_str, re.IGNORECASE)
        if m: return m.group(0)
        return indicator_str[:200].strip()

    def generate_corpus(self, traces_file: str, max_attempts: int = 6, *,
                        reset_before_each_flow: bool = False,
                        pre_step_replay: str = "last"):
        replay_mode = (pre_step_replay or "last").lower()
        if replay_mode not in {"last", "all", "none"}:
            raise ValueError("pre_step_replay must be one of: last, all, none")
        flows = {}
        with open(traces_file, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip(): continue
                step = json.loads(line)
                flows.setdefault(step["flow_id"], []).append(step)

        processed = set()
        if os.path.exists(self.checkpoint_file):
            with open(self.checkpoint_file) as f:
                processed = set(l.strip() for l in f if l.strip())

        print(f"[INFO] Loaded {len(flows)} execution flows for self-play data generation.")

        for flow_id, steps in flows.items():
            if flow_id in processed:
                print(f"[CHECKPOINT] Flow {flow_id} already processed. Skipping.")
                continue

            print(f"\n[FLOW] Generating Data for Flow: {flow_id} ({len(steps)} steps)")

            for t_idx, target_step in enumerate(steps):
                pre_steps = steps[:t_idx]

                if not pre_steps:
                    if reset_before_each_flow:
                        self.state.reset_baseline()
                    self.state.create_snapshot()
                else:
                    self.state.restore_snapshot()
                    if replay_mode == "all":
                        for pre in pre_steps:
                            self.executor.execute(pre.get("ocli_command", ""))
                    elif replay_mode == "last":
                        self.executor.execute(pre_steps[-1].get("ocli_command", ""))
                    self.state.create_snapshot()

                history_str = "\n".join([
                    f"Step {s['step']}: {s.get('ocli_command', '')}" for s in pre_steps
                ])

                valid_token = None
                for k, v in target_step["request"].get("headers", {}).items():
                    if k.lower() == "authorization" and str(v).lower().startswith("bearer "):
                        valid_token = str(v)[7:].strip()

                req_data = target_step["request"].copy()
                if "headers" in req_data:
                    req_data["headers"] = {
                        k: v for k, v in req_data["headers"].items()
                        if k.lower() not in [
                            "host", "user-agent", "accept",
                            "content-length", "content-type", "authorization"
                        ]
                    }

                cmd_parts = target_step.get("ocli_command", "").strip().split(" ")
                exact_cmd = f"{cmd_parts[0]} {cmd_parts[1]}" if len(cmd_parts) >= 2 else "ocli"

                help_text = self.executor.get_help(
                    exact_cmd,
                    target_step.get("openapi_path"),
                    target_step.get("request", {}).get("method", "get")
                )
                if valid_token and hasattr(self.executor, "profile_name"):
                    help_text += (
                        "\n  --api-bearer-token   string   (optional) Overrides the default "
                        "profile JWT authorization token."
                    )

                prompt = (
                    f"=== STATE HISTORY ===\n"
                    f"{history_str if pre_steps else '(No history. This is Step 1)'}\n\n"
                    f"=== TARGET ENDPOINT ORIGINAL REQUEST (For value reference) ===\n"
                    f"{json.dumps(req_data, indent=2)}\n\n"
                    f"=== AVAILABLE CLI FLAGS (FROM OCLI HELP) ===\n{help_text}\n\n"
                    f"=== EXACT CLI COMMAND TO USE ===\n{exact_cmd}\n\n"
                    f"Generate a mutated ocli command targeting this endpoint. "
                    f"You MUST start your command with `{exact_cmd}`."
                )
                messages = [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt}
                ]

                for attempt in range(max_attempts):
                    print(f"    [TEACHER] Requesting mutation. Attempt {attempt + 1}/{max_attempts}...")
                    llm_output = self.llm.query(messages, temperature=(0.1 if attempt == 0 else 0.4))
                    reasoning = llm_output.get("reasoning", "")
                    mutated_cmd = llm_output.get("mutated_command", "")

                    self.state.restore_snapshot()
                    code, stdout, stderr = self.executor.execute(mutated_cmd, bearer_token=valid_token)
                    indicator = (stdout + stderr).lower()

                    if "econnrefused" in indicator or "api-base-url" in indicator:
                        print("[SYSTEM ERROR] Cannot connect to target backend server!")
                        sys.exit(1)

                    is_cli_syntax_error = (
                        code != 0 and "status code" not in indicator and "timed out" not in indicator
                    )
                    is_api_response = "status code" in indicator
                    is_500_crash = (
                        "status code 500" in indicator or
                        "internal server error" in indicator or
                        code == 500
                    )
                    is_2xx_success = (code == 0)
                    core_error = self._clean_error_message(stdout + stderr)

                    # CLI Syntax Error — Critic self-correction loop
                    if is_cli_syntax_error:
                        if attempt < max_attempts - 1:
                            print(f"    [CRITIC] OCLI Syntax Error: '{core_error}'. "
                                  f"Triggering self-correction...")
                            messages.append({"role": "assistant", "content": json.dumps({
                                "reasoning": f"My previous command failed CLI validation: {core_error}",
                                "mutated_command": mutated_cmd
                            }, ensure_ascii=False)})
                            messages.append({"role": "user", "content":
                                f"Execution Error: {core_error}\n\n"
                                "WARNING: You are strictly FORBIDDEN from generating that exact "
                                "command again. Generate a corrected ocli command using ONLY valid "
                                "flags from the AVAILABLE CLI FLAGS."})
                            continue
                        else:
                            print("    [FAIL] CLI Syntax error persisted. Discarded.")
                            break

                    if is_api_response or is_2xx_success:
                        is_security_attack = bool(re.search(
                            r'bola|bfla|bypass|escalation|mass assignment|unauthorized|idor',
                            reasoning, re.IGNORECASE
                        ))
                        is_rbac_bypass = is_2xx_success and is_security_attack

                        # Golden: Exploit confirmed
                        if is_500_crash or is_rbac_bypass:
                            label = "GOLDEN_CRASH" if is_500_crash else "GOLDEN_RBAC_BYPASS"
                            status_val = 201 if is_rbac_bypass else 500
                            print(f"    [SUCCESS] {label} verified!")
                            golden_record = {
                                "messages": [
                                    {"role": "system", "content": self.system_prompt},
                                    {"role": "user", "content": prompt},
                                    {"role": "assistant", "content":
                                        f"<think>\n{reasoning}\nThis targets a deep architectural "
                                        f"flaw. I expect this to bypass validation and hit the "
                                        f"core logic.\n</think>\n\n```bash\n{mutated_cmd}\n```\n"
                                        f"# ASSERT: status == {status_val}"}
                                ]
                            }
                            with open(self.golden_out, "a", encoding="utf-8") as gf:
                                gf.write(json.dumps(golden_record, ensure_ascii=False) + "\n")
                            break

                        # Silver: Defensive boundary — save then nudge
                        else:
                            status_match = re.search(r'status code (\d{3})', indicator, re.IGNORECASE)
                            actual_status = status_match.group(1) if status_match \
                                            else ("200" if is_2xx_success else "400")
                            print(f"    [EXPLORE] Defensive boundary HTTP {actual_status}. "
                                  f"Saving as SILVER, nudging...")
                            silver_record = {
                                "messages": [
                                    {"role": "system", "content": self.system_prompt},
                                    {"role": "user", "content": prompt},
                                    {"role": "assistant", "content":
                                        f"<think>\n{reasoning}\nThis targets a framework "
                                        f"vulnerability. I expect a 4xx defensive boundary.\n"
                                        f"</think>\n\n```bash\n{mutated_cmd}\n```\n"
                                        f"# ASSERT: status == {actual_status}"}
                                ]
                            }
                            with open(self.silver_out, "a", encoding="utf-8") as sf:
                                sf.write(json.dumps(silver_record, ensure_ascii=False) + "\n")

                            if attempt < max_attempts - 1:
                                messages.append({"role": "assistant", "content": json.dumps({
                                    "reasoning":
                                        f"My previous exploit was blocked with HTTP {actual_status}.",
                                    "mutated_command": mutated_cmd
                                }, ensure_ascii=False)})
                                messages.append({"role": "user", "content":
                                    NUDGE_PROMPT_TEMPLATE.format(core_error_message=core_error)})
                                continue
                            else:
                                break

            with open(self.checkpoint_file, "a") as chk:
                chk.write(f"{flow_id}\n")
