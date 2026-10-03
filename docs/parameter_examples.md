# Typed parameter examples

[中文](parameter_examples.zh-CN.md) · [active definitions](../parameters.json) · [strict JSON copy](parameter_examples.json)

The top level of `parameters.json` is an array. The three code blocks below are **complete parameter entries** from the active configuration. Place the entries you need in the array, separated by commas. `initial` sets the starting value; `control` defines permitted adjustments. Run `python run.py doctor` after editing to check the configuration.

## Numeric: `temperature`

```json
{
  "name": "temperature",
  "api_name": "temperature",
  "stage": "completion",
  "type": "number",
  "initial": 0.6,
  "minimum": 0.2,
  "maximum": 2,
  "description": "Sampling randomness. Qwen3 advises against greedy decoding in thinking mode, so the window stops at 0.2.",
  "control": {
    "window": [0.2, 2],
    "denominator": 18
  }
}
```

At `0.6`, Jev can keep, increase, or decrease the value. The step is `(2 − 0.2) / 18 = 0.1`. The floor of 0.2 is deliberate: Qwen3 advises against greedy decoding in thinking mode. Every other numeric window follows vLLM's own validity range. After an increase, a further Choice offers `0.7`, `0.8`, or `0.9`; a decrease offers `0.5`, `0.4`, or `0.3`. Out-of-bounds candidates are omitted.

## Boolean: `ignore_eos`

```json
{
  "name": "ignore_eos",
  "api_name": "ignore_eos",
  "stage": "completion",
  "type": "boolean",
  "initial": false,
  "description": "Continue sampling after EOS; the experiment token cap still applies.",
  "control": {}
}
```

At `false`, Jev chooses keep or turn on. Turning it on directly sets `true`; no exact-value Choice is needed. At `true`, it can keep or turn off. An empty `control` does not freeze the parameter.

## Nullable integer: `logprobs`

```json
{
  "name": "logprobs",
  "api_name": "logprobs",
  "stage": "completion",
  "type": ["integer", "null"],
  "initial": null,
  "minimum": 0,
  "maximum": 20,
  "description": "Observation-only output log probabilities; not a quality control.",
  "control": {
    "enable_candidates": [0, 1, 2],
    "window": [0, 20],
    "denominator": 20
  }
}
```

`null` means the feature is currently off, but the entry still participates in the experiment. If Jev enables it, a further Choice selects `0`, `1`, or `2`. At value `1`, the step is `1`: an increase offers `2`, `3`, or `4`, and disabling returns to `null`. `logprobs` observes output probabilities; it is neither a Jev Score nor a direct answer-quality control.

## Other types

- **Other floats:** `top_p` (initial 0.95, window `[0.05,1]`), `repetition_penalty` (1.0, `[0.5,2]`; below 1 favours repetition), `frequency_penalty` and `presence_penalty` (0, `[-2,2]`), and `min_p` (0, `[0,1]`) use their own windows and denominators. The initial values for temperature, top_p, top_k and min_p are the Qwen3 model card's thinking-mode settings (0.6, 0.95, 20, 0).
- **Integer:** `top_k=20`, practical window `[1,201]`, denominator `40`. One step is 5: increasing offers 25, 30, 35. It also has a separate `disable` action to value 0 and `enable` back to 20. Hard bounds remain `[-1,1000000]`; the huge validation maximum is not used as the step window. Near a boundary, invalid or duplicate values are omitted.
- **Nullable list:** `stop_token_ids` and `allowed_token_ids` need tokenizer-verified integer candidates; the latter must not be set to an empty list. An existing list permits remove or clear. Jev cannot invent list elements.
- **Nullable map:** `logit_bias=null` needs reviewed `control.entries`. An entry is either `{token_id, value}` or a labelled token group `{label, group, token_ids, value}`; the shipped file has twelve groups: hesitation words (Wait, Hmm) and switching words (But, Alternatively, Actually, Maybe) each lowered by 1, 2, 4 or 8, and the end of the thinking block `</think>` raised by 4, 8, 12 or 16. Every ID was taken from the Qwen3 tokenizer and is a single token. Jev picks a group and a strength; choosing another strength for the same group replaces it instead of stacking. The value question shows Jev the label, not raw IDs. JSON records use string keys; the backend converts them back to integer IDs before native construction. An existing map permits removing a group (or a stray key) or clearing it. In a smoke test `</think>` stayed open through 400 tokens at +0 to +12 and closed at token 0 at +16, so only the upper rungs act as a real wrap-up lever.
- **Preset object:** `repetition_detection=null` offers four reviewed presets (`control.presets`, each with a label and a value such as `{max_pattern_size: 30, min_pattern_size: 5, min_count: 3}`). The backend turns the dict into vLLM's `RepetitionDetectionParams`. A detected loop ends the segment with finish reason `repetition`; the run treats this as a normal segment end and continues.
- **Nullable word list:** `bad_words` hard-bans words (`control.candidates`: Wait, Hmm, Alternatively, Actually, Maybe), one added per step.
- **Enum:** `output_kind` begins as `CUMULATIVE` and can switch to the declared alternative `FINAL_ONLY`. The backend maps the JSON string to vLLM's native enum.
- **Other nullable integer:** `prompt_logprobs` follows the same enable and step rules as `logprobs`; it is an observation setting.
- **Other easily changed fields:** `min_tokens` can switch only between `0` and `1`, preserving validity even for a one-token segment. `detokenize`, `skip_special_tokens`, `spaces_between_special_tokens`, `include_stop_str_in_output`, and `flat_logprobs` are boolean switches. The latter flags change observation or output representation; some have no effect unless related features are active.

All 22 current values are included as context for each direction request. Twenty currently have actionable direction options. Only `stop_token_ids` and `allowed_token_ids` require reviewed token candidates and remain hold-only. Technical adjustability does not mean every field is a plausible remedy for an incorrect answer.

The selected field must exist in the installed `SamplingParams`; `python run.py doctor` checks construction without loading a model or contacting Jev. Additional conditional or startup fields in the [full catalog](vllm_catalog_taxonomy.md) need route-specific handling before they can be added here.
