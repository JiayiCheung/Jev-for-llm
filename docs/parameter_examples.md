# Parameter definitions: all types and operations

**English** | [简体中文](parameter_examples.zh-CN.md) | [current implementation](implementation.md) | [README](../README.md)

The [complete example list](parameter_examples.json) is an independent teaching file with unique native parameter names. It is **not** the active configuration, a tuned policy, or a recommendation to enable these rules together. Entries must still pass the installed vLLM and model constraints. Copy only the entry you need into `parameters.json`, replacing any existing entry with the same name/API field. Run `python run.py check` and `python run.py doctor` before an experiment.

Every entry includes `name`, `api_name`, `stage: completion`, `enabled`, `type`, `initial` and `adjustments`. The excerpts below show the varying fields; the linked file contains complete objects. Trigger names remain `narrow_sampling` and `reduce_repetition`. Values change for the **next segment**, while the definition file remains unchanged. `enabled: false` entries are omitted from native keyword arguments; an empty `adjustments` object passes the same value on every segment.

## What is active in this project

The live file is [parameters.json](../parameters.json), not the example JSON below. It defines **20 enabled native `SamplingParams` fields**, but only these three currently have automatic actions:

| Field | Initial value | Trigger → operation | Project bound |
|---|---:|---|---:|
| `temperature` | 0.6 | `narrow_sampling` → add −0.1 | 0–2 |
| `top_p` | 0.95 | `narrow_sampling` → add −0.05 | 0.01–1 |
| `repetition_penalty` | 1.0 | `reduce_repetition` → add +0.05 | 1–1.5 |

The current raw Jev Score triggers are correctness ≤ 2 **or** relevance ≤ 2 for `narrow_sampling`; otherwise repetition ≥ 2.5 for `reduce_repetition`. Pending rollback, optional score stopping and cooldown have priority over these triggers. The 0–4 rollback utility and exact decision order are in [implementation.md](implementation.md). Jev uses **Score**, not generated Choice candidates. It evaluates the completed segment, so adjustments can be submitted only on a subsequent `LLM.generate` call. The prior [Qwen3/Jev parameter-stage checklist](../../Qwen3_Jev_参数调控阶段清单.html) covers Transformers and should not be read as a vLLM runtime test.

The example below deliberately makes `top_p` fixed, whereas the **live** `top_p` is adjustable. Likewise, example `stop`, `bad_words` and token IDs are placeholders, not active settings. Project `minimum`/`maximum` values are policy bounds; constructor acceptance, model compatibility and output effect are separate checks. `check` validates the file shape and action rules, `doctor` checks current initial values against native `SamplingParams`, and a real generation is needed to examine behavior.

## 1. Number: add a bounded delta

```json
{
  "type": "number",
  "initial": 0.6,
  "minimum": 0,
  "maximum": 2,
  "adjustments": {
    "narrow_sampling": {
      "op": "add",
      "value": -0.1
    }
  }
}
```

For `temperature`, 0.6 becomes 0.5. At 0, another −0.1 remains 0 because additions clamp to the configured bounds. This type accepts integers and floating-point numbers, but not booleans.

## 2. Integer: retain an integer result

```json
{
  "type": "integer",
  "initial": 20,
  "minimum": 1,
  "maximum": 100,
  "adjustments": {
    "narrow_sampling": {
      "op": "add",
      "value": -5
    }
  }
}
```

For `top_k`, 20 becomes 15. Integer-only definitions require integer bounds and an integer delta. A value such as 15.5 is rejected.

## 3. Boolean: set a switch

```json
{
  "type": "boolean",
  "initial": false,
  "adjustments": {
    "reduce_repetition": {
      "op": "set",
      "value": false
    }
  }
}
```

For `ignore_eos`, `false` means the model may stop at EOS. `set` assigns the specified boolean directly; strings such as `"false"` are invalid. Here false → false is deliberately a no-op. If current state were true, this rule would restore false. This is syntax demonstration, not a claimed repetition remedy.

## 4. String: replace a stop marker

```json
{
  "type": "string",
  "initial": "END",
  "adjustments": {
    "narrow_sampling": {
      "op": "set",
      "value": "DONE"
    }
  }
}
```

For `stop`, the next call uses `DONE` instead of `END`. `set` replaces the whole value; it does not append text. Stop markers can truncate valid answers and need task-specific selection.

## 5. Array: append and remove elements

```json
{
  "type": "array",
  "initial": [
    "placeholder"
  ],
  "items": {
    "type": "string"
  },
  "adjustments": {
    "reduce_repetition": {
      "op": "append",
      "value": [
        "repeated phrase"
      ]
    },
    "narrow_sampling": {
      "op": "remove",
      "value": [
        "placeholder"
      ]
    }
  }
}
```

For `bad_words`, append produces `["placeholder", "repeated phrase"]`. Reapplying it does not create a duplicate. Remove deletes matching elements: applied to the initial value it produces `[]`. Both action values must be lists, even for one element. The controller chooses one trigger each round, not both. Banning words is a semantic restriction, not automatically beneficial.

## 6. Object: shallow update

```json
{
  "type": "object",
  "initial": {
    "42": -1
  },
  "additional_properties": {
    "type": "number",
    "minimum": -100,
    "maximum": 100
  },
  "adjustments": {
    "narrow_sampling": {
      "op": "update",
      "value": {
        "42": -2,
        "43": 1
      }
    }
  }
}
```

For `logit_bias`, update yields `{"42": -2, "43": 1}`. Existing key 42 changes; new key 43 is added; other existing keys would remain. This is a shallow merge, so a nested object value would be replaced as a whole. Use `set` to replace the entire mapping. JSON keys are strings; token IDs 42 and 43 are illustrative, so inspect the model tokenizer before using them experimentally.

## 7. Null: explicitly disable an optional value

```json
{
  "type": "null",
  "initial": null,
  "adjustments": {}
}
```

For `prompt_logprobs`, this sends null and disables prompt-log-probability collection. The definition accepts **only null**, so setting an integer would fail. Null is different from omitting a field with `enabled: false`: an omitted field uses the backend's default.

## 8. Union: change between null and an integer

```json
{
  "type": [
    "integer",
    "null"
  ],
  "initial": null,
  "minimum": 0,
  "maximum": 20,
  "adjustments": {
    "narrow_sampling": {
      "op": "set",
      "value": 5
    }
  }
}
```

For `logprobs`, null → 5 enables collection on the next call. `set` can change types within the declared union. A `set` action with null would disable it again. Numeric bounds apply to the integer branch; `add` is not accepted for a nullable numeric definition. For nullable arrays/objects, use `set` to create a list/object before append/remove/update.

## 9. Enabled but fixed

```json
{
  "name": "top_p",
  "enabled": true,
  "initial": 0.95,
  "adjustments": {}
}
```

The full example includes its numeric type and bounds. The value is passed on every call, but no controller trigger changes it. This applies even in adaptive mode.

## 10. Disabled override

```json
{
  "name": "min_p",
  "enabled": false,
  "initial": 0,
  "adjustments": {}
}
```

The definition remains visible, but the project omits it from runtime values and native keyword arguments. vLLM supplies its default. This does not disable all minimum-probability logic inside the backend; it disables this project's explicit override.

## Operation summary

| Operation | Accepted value | Effect |
|---|---|---|
| add | Numeric delta | Add and clamp to configured bounds |
| set | Any value matching the schema | Replace the complete value |
| append | List of valid elements | Add missing elements to an existing list |
| remove | List of valid elements | Remove matching elements from an existing list |
| update | Object patch | Shallow-merge into an existing object |

Each resulting value is validated after the operation. Types/bounds describe accepted data; they do not prove scientific usefulness or support every native parameter combination.
