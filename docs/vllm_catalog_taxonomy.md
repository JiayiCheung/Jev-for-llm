# vLLM checklist taxonomy for the Jev controller

This audit covers every one of the 1,181 route-specific entries embedded in the local `Qwen3-0.6B_vLLM_parameter_checklist.html` snapshot (vLLM `0.29.0+cu132`, audited 2026-09-30). The [CSV inventory](vllm_catalog_taxonomy.csv) preserves each entry's original ID, batch, route, declared type, default, domain, execution stage, value family, controller class, and proposed Choice/step rule. Regenerate it with [the classifier](../scripts/classify_vllm_checklist.py) when the source checklist changes. The HTML explicitly labels this as a test plan rather than proof of runtime support or complete legal bounds.

The 1,181 entries are **not** 1,181 interchangeable functions or live controls. The source counts 1,051 native field entries, 65 Python argument entries, 5 CLI switches, 7 procedures, 1 Qwen template option, and 52 excluded internal entries. Names recur across distinct interfaces. In particular, HTTP request fields must not be forwarded as Python `SamplingParams` keywords, and engine-startup or nested engine fields cannot be changed between calls of the current loaded `LLM` instance.

The classifier first records the owning route and execution stage, then the declared value shape. It does not infer control eligibility from `int` or `float` alone. Its classes cover Python sampling, Python entry points and prompt construction, tokenization endpoints, HTTP requests, startup and nested engine configuration, nested request schemas, beam search, the Qwen template option, project integration tests, procedures, and exclusions. No catalog ID is dropped; unknown routes fail the audit rather than silently receiving a generic step.

Each CSV row also carries `value_action_family` and `generic_step_eligibility`. These describe possible edits for the **declared value shape**, not permission to expose that field to the current controller. The declared-type buckets contain 284 booleans, 222 integers, 60 floats, 150 strings, 77 collections, 68 mappings, 34 discrete values, 22 unions containing collections, 28 other unions or structures, and 236 fields needing schema or validator review. Complex structures, nullable states, and nested numeric values do not acquire a step rule from their names alone.

## Current Python sampling boundary

The checklist has 39 route-specific entries under `Python / SamplingParams`. The current 20 representative entries in `parameters.json` all match one of them. The remaining entries are still classified, but merely appearing in `SamplingParams` does not make a field suitable for score-driven adaptation. The CSV's `in_parameters_json` column is regenerated from the current selection.

- Seven quality-oriented numeric controls: `temperature`, `top_p`, `top_k`, `repetition_penalty`, `min_p`, `presence_penalty`, `frequency_penalty`.
- Four termination controls: `stop`, `stop_token_ids`, `ignore_eos`, `min_tokens`.
- Three token constraints: `logit_bias`, `allowed_token_ids`, `bad_words`.
- Four observation controls: `logprobs`, `prompt_logprobs`, `logprob_token_ids`, `flat_logprobs`.
- Six output/stream representation controls: `detokenize`, `skip_special_tokens`, `spaces_between_special_tokens`, `include_stop_str_in_output`, `output_kind`, `stream_interval`.
- Three runner-owned experiment values: `n`, `seed`, `max_tokens`.
- Seven conditional features requiring their own source and prerequisite review.
- Five excluded or derived fields.

These counts sum to 39. Only the first seven are general numeric answer-quality candidates. `min_tokens` has a separate conditional rule; it is constrained by the next call's `max_tokens`. The observation and display fields remain visible in the inventory but should not be treated as remedies for low correctness or high repetition. The existing runner owns `max_tokens`, `seed`, and `n`; in particular, no remaining-token budget is sent to Jev as an adaptive choice.

## Proposed direction and magnitude rules

For a numeric control, Jev first chooses `keep`, `increase`, or `decrease`. After that answer, the controller offers up to three **exact values**: current value plus or minus one, two, or three steps. The step is the practical control-window width divided by the denominator below. The practical window is separate from the declared or validated hard bounds. Integer results are quantized and deduplicated. Invalid or duplicate candidates are removed, so fewer than three may remain near a boundary. These are provisional research settings, not vLLM defaults or measured optima.

- `temperature`: control window 0–2; denominator 20; step 0.1.
- `top_p`: 0.01–1; denominator 100; step 0.0099. From 0.95 this gives usable upward candidates without jumping immediately out of range.
- `min_p`: 0–1; denominator 100; step 0.01.
- `repetition_penalty`: 1–1.5; denominator 20; step 0.025 under the project's current bounds.
- `presence_penalty` and `frequency_penalty`: each −2–2; denominator 100; step 0.04.
- `top_k`: proposed practical window 1–101; denominator 20; integer step 5. The `parameters.json` maximum of 1,000,000 is a validation ceiling, not a useful step window. Values 0 and −1 are separate disable states, not points on the 1–101 grid.
- `min_tokens`: conditional practical window 0–128; denominator 20; quantized integer step near 6. The runner must additionally enforce the next call's actual `max_tokens`; this value is not inferred from the Jev score.

Boolean controls use `keep`/`turn_on`/`turn_off` and have no magnitude. Nullable numeric fields first choose an enable value from reviewed starting candidates; once numeric, the current controller offers bounded one-, two-, or three-step increases and decreases, plus disabling back to `null`. `logprobs` and `prompt_logprobs` are instrumentation, not answer-quality controls. String, list, and mapping fields require verified candidate strings, words, token IDs, or object entries before `set`, `add`, `remove`, or `clear` can be offered. A type declaration alone cannot invent safe content. `logit_bias` additionally needs a validated token ID and a separately bounded coefficient. Specialized features such as structured outputs or speculative decoding cannot inherit the generic numeric rule.

For other routes, even a declared integer or float is only a **conditional** directional candidate. Its owning interface, complete legal bounds, practical control window, and point of effect must be verified first. Startup fields normally require engine reconstruction; HTTP and other Python entry points are separate experiments. Without that evidence, the catalog deliberately assigns neither a 1/20 nor a 1/100 step and does not offer the field in the current per-chunk Choice.

The current controller now builds typed Score, direction Choice, and exact-value Choice requests for the selected subset. The taxonomy remains a broader inventory, not a promise that all 1,181 routes are implemented or runtime-verified. Runtime eligibility and proposed step sizes require isolated tests before enabling additional controls.
