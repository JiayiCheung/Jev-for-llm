# Current implementation: Qwen3 + Jev + native vLLM

[简体中文详细版](implementation.zh-CN.md) · [English README](../README.md) · [parameter examples](parameter_examples.md)

This describes the code and configuration in `Code/` as of 2026-10-01. The older [Qwen3/Jev parameter-stage audit](../../Qwen3_Jev_参数调控阶段清单.html) studied Transformers 4.57.6; its per-token processors and example controller pseudocode are **not** this runner's vLLM implementation. The active native parameter list is `parameters.json`.

## Ownership and when a change takes effect

| Layer | Source | Effective time |
|---|---|---|
| Model and engine | `config.json` → `engine`, `runtime`; `backend.py` | Engine creation; changing these requires a new process/engine. |
| Prompt | `generation.enable_thinking`; Qwen chat template in `backend.py` | Before tokenizing each task. It is not a per-token thinking-budget control. |
| Generation schedule | `generation.chunk_tokens`, `total_tokens`, `max_rounds`, `engine.max_model_len`, `experiment.max_jev_calls`; `runner.py` | Before every segment; the smallest remaining budget determines `max_tokens`. |
| Sampling and output options | The 20 enabled `stage: completion` entries in `parameters.json`; `parameters.py` → native `vllm.SamplingParams` | Before each `LLM.generate` call. A decision cannot alter tokens within the running call. |
| Evaluation | `jev_questions.json`; `adapters.py` and `clients.py` | After a nonempty segment; one HTTPS Jev request carries four Score questions. |
| Decision | `config.json` → `policy`; `policy.py` | After Jev returns; proposed values can be sent only in the **next** segment. |

`run.py` dispatches to `cli.py`. `PythonBackend` lazily creates one `vllm.LLM` in the current interpreter and reuses it. There is no local OpenAI-compatible server, backend selector or configured Python executable. Only Jev uses HTTP(S).

## One task/seed/mode run

1. `runner.py` applies Qwen's chat template to the task prompt. A separate run starts from the initial values in `parameters.json`.
2. Before each call, the runner builds `prompt_token_ids = original_prompt_ids + all_generated_ids`, a per-segment `seed = initial_seed + step`, and `max_tokens = min(chunk_tokens, remaining_total_tokens, remaining_context_tokens)`. The runner requires exactly one candidate. `seed`, `max_tokens`, the prompt and candidate count are runner-owned, so the parameter file cannot override them.
3. The backend builds a fresh `SamplingParams` with the current values and calls `LLM.generate`. It returns native output text, token IDs, finish/stop reasons and any enabled log-probability records. The runner independently decodes accumulated token IDs with `skip_special_tokens=False` to obtain the raw text sent to Jev and saved in `answer.txt`.
4. Jev receives `model`, the four Score rubrics and `state = {task, generated, recent, step}`. Neither the task's reference answer nor a generated list of choices is sent. `parse_scores` checks each score's range, probability-level keys and probability sum. The controller uses the **numeric Score fields**; probabilities are validated and recorded, but are not themselves decision inputs.
5. The controller decides `hold`, `adjust`, `rollback` or `stop`. The runner checks model stop and all budgets before applying proposed parameters. Inspect the **next** round's `applied_parameters` / `generation_request` to confirm execution; a decision row by itself is not proof of a subsequent call.

Each segment is a new generation call with prior output converted into prompt tokens. This can reset per-call state: presence/frequency penalties concern the current call's newly generated tokens, while repetition penalty can see tokens now in the prompt. Stop-string matching across segment boundaries is not guaranteed. Prefix caching does not make the run equivalent to one uninterrupted generation.

## Current decision rule

The rubrics are correctness, relevance, repetition and completeness, each currently scored from 0 to 4. Higher repetition is worse. Trigger and stopping thresholds compare **raw** Score values. For the current `config.json`:

| Condition, checked in order after pending feedback | Result |
|---|---|
| `fixed` mode | Hold the initial parameters; Jev is still called after each segment. |
| An adjustment is pending and the 0–4 composite utility fell by **more than** `rollback.score_drop = 0.6` | Restore the previous parameter values and enter cooldown. Generated text remains. |
| `stopping.enabled = true` and completeness ≥ 4, correctness ≥ 3, relevance ≥ 3 | Propose score-based stop. Currently `enabled = false`; `compare` also disables it in both groups. |
| Within `cooldown_rounds = 1` after a change | Hold. |
| Correctness ≤ 2 **or** relevance ≤ 2 | `narrow_sampling`: temperature −0.1 and top_p −0.05, clamped to their configured bounds. |
| Otherwise repetition ≥ 2.5 | `reduce_repetition`: repetition_penalty +0.05, clamped to its bound. |
| Otherwise, or if an action leaves all values unchanged | Hold. |

Pending feedback is evaluated before a new trigger. A retained change may then be held by cooldown. The current utility is `4 × weighted_mean(correctness/max, relevance/max, completeness/max, 1 − repetition/max)`; with the five-level rubrics and current weights this equals `0.45·correctness + 0.30·relevance + 0.15·completeness + 0.10·(4 − repetition)`. It measures the controller's chosen heuristic, not answer accuracy. Rollback is based on association across adjacent segments, not a causal test. Old run records used a different utility scale and should not be compared numerically with new ones.

Only three of the 20 enabled native fields currently have nonempty automatic rules: `temperature`, `top_p` and `repetition_penalty`. Other fields are passed with their initial values. Adding a new trigger name or control stage needs code changes; adding a field to JSON alone does not create a new adapter.

## Validation and records

`check` validates configuration and task loading without importing vLLM. `doctor` imports the installed vLLM and constructs `SamplingParams` from initial values without loading the model. `smoke` loads the model and generates up to eight tokens without Jev. `run` uses the configured mode; `compare` runs fixed then adaptive for every task/seed, with score stopping disabled for both. Both modes call Jev. `summarize` reads existing records and does not grade answers.

Each run writes `outputs/<timestamp>_<mode>/result.json` and `answer.txt`, saving incrementally. The saved config redacts `jev.api_key`; the record includes the request, response, timing, Score fields, decision and `decision_will_execute`. `status: completed` means the loop ended without an exception, **not** that the mathematical answer was correct. The historical 2026-09-30 outputs were produced under an older policy, so they do not verify today's thresholds or adaptive adjustments. There is no automatic reference-answer grader or no-Jev continuous baseline.
