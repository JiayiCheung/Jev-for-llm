# Transformers → native vLLM: migration boundary

[简体中文详细版](transformers_to_vllm.zh-CN.md) · [current implementation](implementation.md) · [active parameter definitions](../parameters.json)

The [earlier Chinese parameter-stage checklist](../../Qwen3_Jev_参数调控阶段清单.html) inventories Qwen3-0.6B under **Transformers 4.57.6** and PyTorch 2.6.0. Its value ranges, per-token hook examples and practice labels describe that environment. The current project calls Python `vllm.LLM.generate` with a new `vllm.SamplingParams` **once per segment**. A shared parameter name is not evidence of identical implementation, range or effect.

| Earlier Transformers concept | Current project / native vLLM location | Important difference |
|---|---|---|
| `model.generate(...)` | `backend.py` → persistent `vllm.LLM.generate(...)` | Not an HTTP completion request or a Transformers `GenerationConfig` call. |
| `max_new_tokens` | Runner-owned `SamplingParams.max_tokens` | Computed anew from chunk, total-token and remaining context budgets; not an editable `parameters.json` entry. |
| `min_new_tokens` | Native `min_tokens` (not in the current representative selection) | Per **segment**, and must fit the effective `max_tokens`. |
| `do_sample=False` | `temperature=0` for greedy decoding | No `do_sample` key is sent. |
| `temperature`, `top_p`, `top_k`, `repetition_penalty` | Same keyword names in `SamplingParams` | Use project bounds plus installed vLLM validation; do not import Transformers defaults/ranges. |
| `stop_strings` | `SamplingParams.stop`; also `stop_token_ids`, `ignore_eos` | Stop matching and finish reasons are scoped to a segment. |
| `num_return_sequences` | Runner requires exactly one output | `n` and `best_of` are reserved from user-selected parameter definitions. |
| Output scores | `logprobs`, `prompt_logprobs` | Native vLLM records are captured when enabled; Jev's four Scores are separate evaluation results. |
| Logits processor / streamer / dynamic per-token callback | No equivalent hook in this runner | Current policy observes only completed segments and changes the next call. |
| Device, dtype, context and optional sampler | `config.json` → `engine` / `runtime` | Chosen at engine creation, not per segment. |
| `enable_thinking` | Qwen tokenizer chat-template argument | Chosen before prompt tokenization; not a numerical thinking budget. |

`parameters.json` currently defines 20 representative native `SamplingParams` fields. Every listed entry participates; remove the entry to omit it. All are checked for name/type at startup; `doctor` constructs the initial native values, and every segment is validated again. The controller builds typed Jev Choices for eligible fields; fields with no reviewed concrete candidates remain hold-only. `api_name` is the native Python keyword, not an HTTP field. An `initial` value of `null` remains a present native parameter value, not an exclusion flag.

The previous Transformers-specific evidence cannot establish that a vLLM value works with this model or changes output. `check` tests project configuration, `doctor` checks native constructor acceptance of initial values, and `smoke` executes one short model call. Runtime records prove which values were **submitted** in subsequent segments; establishing a behavioral effect needs a controlled comparison. The project does not implement arbitrary mid-token hot changes, a Transformers processor chain, or a no-Jev continuous baseline.

For typed `set` / `add` / `append` / `remove` / `update` examples, use [parameter_examples.md](parameter_examples.md) or [中文版](parameter_examples.zh-CN.md). Those examples are educational and intentionally differ from the active rules.
