# P2S Model, Training, Export, and Serving

The P2S framework and the model-training environment are deliberately separated:

- P2S captures/compiles traces, executes self-play, labels results, and builds `final_training_dataset.jsonl`.
- The retained Qwen3.5-9B specialization is a downstream SFT procedure using Unsloth/TRL on an A100 80 GB.

This separation keeps the core SDK usable without requiring the training stack.

## 1. Training-data source

Generate the corpus with:

```bash
p2s generate-data \
  --config configs/research/aitasker_training.toml \
  --workdir runs/aitasker

p2s prepare-dataset \
  --config configs/research/aitasker_training.toml \
  --workdir runs/aitasker
```

Retained corpus audit values:

```text
raw silver          1,917
deduplicated silver 1,782
unique candidate golden 44
final samples       2,266
```

The 44-candidate scarcity is an observed result of that source run, not a constant that a new target must reproduce.

## 2. Base architecture

```text
Qwen3.5-9B
```

The source-corpus generator uses the **base, pre-fine-tuning Qwen3.5-9B architecture**. No larger teacher supplies task labels; live backend execution supplies the label signal.

## 3. Retained SFT configuration

The retained training notebook uses:

```text
loader                 Unsloth FastVisionModel
base                    unsloth/Qwen3.5-9B
quantization            4-bit NF4 load
vision layers           not fine-tuned
LoRA rank               32
LoRA alpha              64
LoRA dropout            0.05
target modules          q/k/v/o projections, gate/up/down, lm_head, embed_tokens
max sequence            24,576
batch                    1
gradient accumulation   4
effective batch         4
epochs                   6
learning rate            2e-4
scheduler                cosine with restarts, 6 cycles
warmup                   50 steps
optimizer                AdamW 8-bit
weight decay             0.01
max grad norm            1.0
NEFTune alpha            5.0
precision                bfloat16
seed                     3407
```

Response-only masking uses the Qwen chat boundaries:

```text
instruction_part = "<|im_start|>user\n"
response_part    = "<|im_start|>assistant\n"
```

Only assistant-response tokens contribute supervised loss.

## 4. Expected outputs

The notebook exports three Hugging Face-format families:

```text
qwen35-9b-p2s-lora/
qwen35-9b-p2s-merged-16bit/
qwen35-9b-p2s-merged-4bit/
```

The corresponding public model repositories used by this project are:

```text
minhhungg/qwen35-9b-p2s-lora
minhhungg/qwen35-9b-p2s-merged-16bit
minhhungg/qwen35-9b-p2s-merged-4bit
minhhungg/p2s_gguf
```

## 5. GGUF conversion

The retained conversion uses the merged 16-bit checkpoint as the canonical source:

```bash
python convert_hf_to_gguf.py <MERGED_16BIT_DIR> \
  --outfile qwen35-9b-p2s-f16.gguf \
  --outtype f16

./llama-quantize \
  qwen35-9b-p2s-f16.gguf \
  qwen35-9b-p2s-Q8_0.gguf \
  Q8_0
```

The reported evaluation uses the Q8_0 artifact. A Q5_K_M fallback is not part of the reported model comparison.

If the conversion-time Transformers version rejects the Qwen3.5 `TokenizersBackend` tokenizer class, the retained workaround changes the conversion copy of `tokenizer_config.json` to `PreTrainedTokenizerFast`. Treat this as a conversion-tool compatibility workaround, not a model/training change.

## 6. llama.cpp serving

Serve the fine-tuned model on port `8081`:

```bash
llama-server -m qwen35-9b-p2s-Q8_0.gguf \
  --host 0.0.0.0 \
  --port 8081 \
  -ngl 99 \
  -c 262144 \
  --threads 8
```

P2S configs expect the OpenAI-compatible API at:

```text
http://localhost:8081/v1
```

## 7. Base-Qwen control

The untuned Qwen3.5-9B control should use the same Q8_0 quantization level and the same configured context budget when reproducing the paper comparison. The original study used a different serving wrapper for the base model (LM Studio) than for the fine-tuned model (bare llama-server); retain that as a limitation unless you deliberately run a new controlled serving-wrapper ablation.

## 8. DeepSeek controls and AutoRestTest

The Track-A P2S-harness DeepSeek control uses:

```text
deepseek-v4-flash
```

The **completed original AutoRestTest run also used DeepSeek-V4-Flash**. Older archival AutoRestTest notes containing a local base-Qwen template are superseded for final-run reproduction.
