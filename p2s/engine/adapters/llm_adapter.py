"""
P2S LLM Adapters: Standardized interface for querying language models.
Supports OpenAI-compatible APIs and local HuggingFace Transformers (Safetensors).
Includes 3-Tier M2 (predicted_status) extraction.
"""
from abc import ABC, abstractmethod
import json
import re

class BaseLLMAdapter(ABC):
    @abstractmethod
    def query(self, messages: list, temperature: float) -> dict:
        pass

    def _parse_output(self, raw_text: str) -> dict:
        """Robust multi-pass extractor for P2S formatting & 3-tier M2 status extraction."""
        raw_text = raw_text.strip()
        parsed = {}

        # 1. Code-Fence Extraction (P2S Native Format)
        bash_match = re.search(
            r'```[a-zA-Z]*\s*\n?(ocli[\s\S]*?)\n?\s*```', raw_text, re.IGNORECASE
        )
        if bash_match:
            cmd = bash_match.group(1).strip()
            cmd = re.sub(r'\n#\s*ASSERT:.*$', '', cmd, flags=re.MULTILINE).strip()
            cmd = re.sub(r'#\s*ASSERT:.*', '', cmd).strip()
            fence_start = raw_text.find('```')
            reasoning = re.sub(r'</?think>', '', raw_text[:fence_start]).strip() \
                        if fence_start > 0 else ""
            if cmd:
                parsed = {"reasoning": reasoning, "mutated_command": cmd}

        # 2. JSON Extraction (DeepSeek / Base Model Fallback)
        if not parsed:
            json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if json_match:
                try:
                    parsed = json.loads(json_match.group(0), strict=False)
                except json.JSONDecodeError:
                    pass

        # 3. Think-tag + bare command fallback
        if not parsed:
            reasoning = ""
            tm = re.search(r'<think>(.*?)</think>', raw_text, re.DOTALL | re.IGNORECASE)
            if tm: reasoning = tm.group(1).strip()
            cmd_match = re.search(r'^(ocli\s+.+)$', raw_text, re.MULTILINE | re.IGNORECASE)
            cmd = cmd_match.group(1).strip() if cmd_match else ""
            cmd = re.sub(r'#\s*ASSERT:.*', '', cmd).strip()
            if cmd or reasoning:
                parsed = {"reasoning": reasoning, "mutated_command": cmd}

        # M2 Three-Tier Prediction Extraction
        predicted_status = None
        # Tier 1: JSON key
        _ps = parsed.get("predicted_status")
        if _ps is not None:
            try: predicted_status = int(_ps)
            except (ValueError, TypeError): pass

        # Tier 2: Raw Response ASSERT comment
        if predicted_status is None:
            assert_match = re.search(r'#\s*ASSERT:\s*status\s*==\s*(\d{3})', raw_text)
            if assert_match:
                predicted_status = int(assert_match.group(1))

        # Tier 3: Reasoning / Command Fallback
        if predicted_status is None:
            combined_text = (parsed.get("reasoning", "") or "") + " " + \
                            (parsed.get("mutated_command", "") or "")
            assert_match = re.search(r'#\s*ASSERT:\s*status\s*==\s*(\d{3})', combined_text)
            if assert_match:
                predicted_status = int(assert_match.group(1))

        parsed["predicted_status"] = predicted_status
        parsed["_raw_response"] = raw_text
        return parsed


class OpenAICompatAdapter(BaseLLMAdapter):
    """Works with OpenAI, DeepSeek, LM Studio, and llama.cpp."""

    def __init__(self, base_url: str, api_key: str, model_name: str):
        from openai import OpenAI
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model_name = model_name

    def query(self, messages: list, temperature: float) -> dict:
        resp = self.client.chat.completions.create(
            model=self.model_name, messages=messages,
            temperature=temperature, max_tokens=8192
        )
        content = resp.choices[0].message.content or ""
        reasoning_content = getattr(resp.choices[0].message, "reasoning_content", "")
        combined = (reasoning_content + "\n" + content).strip() if reasoning_content else content
        return self._parse_output(combined)


class TransformersAdapter(BaseLLMAdapter):
    """Runs local Safetensor/PyTorch models directly on GPU."""

    def __init__(self, model_path: str):
        self._apply_runtime_patches()
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[*] Loading Local Transformers Model: {model_path} on {self.device}...")
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_path, device_map="auto", torch_dtype=torch.bfloat16, trust_remote_code=False
        )
        self.model.eval()

    def _apply_runtime_patches(self):
        """Fixes PyTorch weight-init and Safetensors double-prefix key mapper bugs."""
        try:
            import torch, torch.nn.init as init, safetensors.torch, safetensors

            if hasattr(init, "_no_grad_normal_"):
                orig = init._no_grad_normal_
                def patched(tensor, mean=0., std=1., generator=None):
                    return tensor if tensor.dtype in (torch.uint8, torch.int8) \
                           else orig(tensor, mean, std, generator)
                init._no_grad_normal_ = patched

            orig_load_file = safetensors.torch.load_file
            def patched_load_file(filename, device="cpu"):
                sd = orig_load_file(filename, device=device)
                PREFIX = "model.language_model.language_model."
                return {
                    ("model." + k[len(PREFIX):] if k.startswith(PREFIX) else k): v
                    for k, v in sd.items()
                }
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
                def keys(self): return self._keys_list
                def get_tensor(self, k): return self.handle.get_tensor(self._fwd.get(k, k))
                def get_slice(self, k): return self.handle.get_slice(self._fwd.get(k, k))
                def __enter__(self): return self
                def __exit__(self, *a): pass
            safetensors.safe_open = PatchedSafeOpen
        except ImportError:
            pass

    def query(self, messages: list, temperature: float) -> dict:
        import torch
        text = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self.tokenizer(text, return_tensors="pt").to(self.device)
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs, max_new_tokens=8192, temperature=temperature,
                do_sample=(temperature > 0),
                pad_token_id=self.tokenizer.eos_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
                repetition_penalty=1.1
            )
        raw = self.tokenizer.decode(
            outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True
        )
        return self._parse_output(raw)
