# Typed parameter examples

[中文](parameter_examples.zh-CN.md) · [active definitions](../parameters.json) · [strict JSON copy](parameter_examples.json)

The active `parameters.json` contains 20 representative native `SamplingParams` fields. `jev_requests.py` reads each entry's `type` and `control` metadata to build typed Choices. The full JSON copy is a syntax example; edit the active file to change a run. The old `adjustments` trigger map is rejected.

- **Float:** `temperature=0.6`, control window `[0,2]`, denominator `20`. Direction options are keep/increase/decrease. An increase offers exact values `0.7`, `0.8`, and `0.9`; a decrease offers `0.5`, `0.4`, and `0.3`. `top_p`, `repetition_penalty`, `frequency_penalty`, `presence_penalty`, and `min_p` use their own windows and denominators.
- **Integer:** `top_k=20`, practical window `[1,101]`, denominator `20`. One step is 5: increasing offers 25, 30, 35. It also has a separate `disable` action to value 0 and `enable` back to 20. Hard bounds remain `[-1,1000000]`; the huge validation maximum is not used as the step window. Near a boundary, invalid or duplicate values are omitted.
- **Boolean:** `ignore_eos=false` offers keep/turn_on. Once true, it offers keep/turn_off. The exact result follows directly from the selected direction, so there is no third Jev request.
- **Nullable list:** `stop_token_ids` and `allowed_token_ids` need tokenizer-verified integer candidates; the latter must not be set to an empty list. An existing list permits remove or clear. Jev cannot invent list elements.
- **Nullable map:** `logit_bias=null` needs reviewed `control.entries` with integer `token_id` and bounded numeric `value`. JSON records use string keys; the backend converts them back to integer IDs before native construction. An existing map permits removing an entry or clearing it. Confirm the ID with the actual model tokenizer before adding it.
- **Enum:** `output_kind` begins as `CUMULATIVE` and can switch to the declared alternative `FINAL_ONLY`. The backend maps the JSON string to vLLM's native enum.
- **Nullable integer:** `logprobs=null` and `prompt_logprobs=null` can enable from reviewed starting values `0`, `1`, or `2`. Once enabled, their `[0,20]` window and denominator `20` give an integer step of 1: from 1, increasing offers 2, 3, 4, decreasing offers 0, and disabling returns to `null`. These are instrumentation controls, not Jev Score or answer-quality controls.
- **Other easily changed fields:** `min_tokens` can switch only between `0` and `1`, preserving validity even for a one-token segment. `detokenize`, `skip_special_tokens`, `spaces_between_special_tokens`, `include_stop_str_in_output`, and `flat_logprobs` are boolean switches. The latter flags change observation or output representation; some have no effect unless related features are active.

All 20 current values are included as context for each direction request. Seventeen currently have actionable direction options. Only `stop_token_ids`, `allowed_token_ids`, and `logit_bias` require reviewed token candidates and remain hold-only. Technical adjustability does not mean every field is a plausible remedy for an incorrect answer.

The selected field must exist in the installed `SamplingParams`; `python run.py doctor` checks construction without loading a model or contacting Jev. Additional conditional or startup fields in the [full catalog](vllm_catalog_taxonomy.md) need route-specific handling before they can be added here.
