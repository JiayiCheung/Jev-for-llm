# Jev and vLLM Inference Control

**English** | [简体中文](docs/README.zh-CN.md) | [Project Website](https://jiayicheung.github.io/Jev-for-llm/)

Qwen generates text locally through the Python vLLM API. Jev evaluates each segment using four Score rubrics. A configurable controller chooses the next segment's parameters. The model stays loaded throughout one process. Only Jev uses HTTPS; no local API server is required.

## Contents

- [Environment and installation](#1-environment-and-installation)
- [Layout and ownership](#2-layout-and-ownership)
- [File formats and configuration](#3-file-formats-and-configuration)
- [Call flow and decision rules](#4-call-flow-and-decision-rules)
- [Run modes](#5-run-modes)
- [First run and results](#6-first-run-and-results)
- [Tests and troubleshooting](#7-tests-and-troubleshooting)
- [Interpretation limits](#8-interpretation-limits-and-further-reading)

## 1. Environment and installation

### 1.1 Create an isolated environment and obtain the repository

Install Git, Conda and a suitable NVIDIA driver first. Run in a terminal from the parent directory where you want the checkout:

```shell
conda create -n jev-vllm python=3.12 -y
conda activate jev-vllm
python -m pip install --upgrade pip
git clone https://github.com/JiayiCheung/Jev-for-llm.git
cd Jev-for-llm
```

All commands below run from this repository root, where `run.py` is located. The repository contains machine-specific configuration, so cloning alone is not sufficient: update the paths in section 1.4 before running checks. If you already have a working vLLM environment, activate it and skip dependency reinstallation.

### 1.2 Install the GPU inference backend

This project does not bundle model weights or install vLLM through its package metadata. On Windows, use the [Windows community build instructions](https://github.com/SystemPanic/vllm-windows#installing-an-existing-release-wheel), select a [release wheel](https://github.com/SystemPanic/vllm-windows/releases) matching its stated Python, PyTorch and CUDA requirements, and download it. Then replace the example filename with the actual downloaded file:

```powershell
python -m pip install "C:/Downloads/ACTUAL_RELEASE_WHEEL.whl"
```

The filename is a placeholder, not a release artifact. There is no single wheel command suitable for every Windows environment. The project was exercised with Python 3.12 and a Windows vLLM 0.29.0 build; a fresh installation must be checked independently.

Verify the selected interpreter and GPU visibility:

```powershell
python -c "import sys, torch, vllm; print(sys.executable); print(vllm.__version__); print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available())"
```

The last line should be `True`. This checks GPU visibility, not successful model inference.

### 1.3 Install this project and download model files

```shell
python -m pip install -e .
python -m pip install huggingface_hub
hf download Qwen/Qwen3-0.6B --local-dir models/Qwen3-0.6B
```

The [Hugging Face CLI](https://huggingface.co/docs/huggingface_hub/guides/cli) downloads weights, tokenizer and configuration files. If a complete local model already exists, skip the download and use that directory. Editable installation makes the package importable; `run.py` also supports execution directly from the checkout.

### 1.4 Configure the local paths and evaluator

Edit the existing `paths` object in `config.json` to use your machine. This fragment assumes the download command above:

```json
"paths": {
  "model": "models/Qwen3-0.6B",
  "dataset": "data/tasks.jsonl",
  "outputs": "outputs"
}
```

Activate your environment before running, or explicitly use its Python executable. Keep the other configuration sections and fill `jev.api_key` directly; no separate credential input is required.

## 2. Layout and ownership

```text
Jev-for-llm/
  run.py                 Command-line entry point
  config.json            Paths, engine, budgets, API key and policy thresholds
  parameters.json        Selected native fields, types, defaults and actions
  jev_questions.json     Four evaluator rubrics
  pyproject.toml         Package/build metadata
  data/                  Active tasks and sampling provenance
  src/jev_vllm/          Implementation
  outputs/               Generated experiment records
  README.md              Project guide
```

## 3. File formats and configuration

The three configuration files use JSON structure with custom `#` line comments. Strings require double quotes; booleans are `true`/`false`; an absent optional value is `null`. No trailing commas, `//` comments or block comments. A plain `json.load` cannot read these commented files: use `load_config`. VS Code's YAML association only supplies highlighting; ordinary YAML syntax is not accepted.

Keep code, prompts and configuration comments in English. Chinese is provided in this documentation only. Relative configuration paths resolve from the configuration file's directory. JSON Windows paths need escaped backslashes (`"E:\\Models\\Qwen3-0.6B"`) or forward slashes.

| Section in config.json | Controls |
|---|---|
| paths | Model, dataset, output directory |
| engine | LLM constructor: dtype, context size, sequence capacity, GPU memory fraction, eager execution, tensor parallelism |
| runtime | Optional FlashInfer sampler switch |
| jev | HTTPS base URL, endpoint, model, direct API key, timeout, rubric file |
| generation | Thinking template, segment/total token budgets, round cap |
| parameters_file | Path to the selected parameter definitions |
| experiment | fixed/adaptive mode, seeds, per-experiment Jev call cap |
| policy | cooldown, stopping thresholds, rollback threshold, utility weights |

The project always uses the active Python interpreter and native vLLM. `engine` settings apply when constructing the model; selected SamplingParams apply to the next generation call.

### API key: configuration only

Within the existing `jev` object, set:

```json
"api_key": "YOUR_TYPESAFE_API_KEY"
```

The client reads this field directly. There is no environment-variable lookup or interactive key prompt. Keep the real key in your local configuration; replace it with a placeholder before publishing that file. Saved experiment configuration redacts `api_key`.

The endpoint is `https://api.typesafe.ai/v1/systemone`, with Bearer authentication. See [TypeSafe's API quickstart](https://docs.typesafe.ai/introduction/quickstart). No TypeSafe SDK installation is required: this implementation uses Python's standard-library HTTP client.

### Selecting generation parameters

`parameters.json` is a list of definitions. Example entry:

```json
{
  "name": "temperature",
  "api_name": "temperature",
  "stage": "completion",
  "type": "number",
  "initial": 0.6,
  "minimum": 0,
  "maximum": 2,
  "description": "Sampling randomness",
  "control": {"window": [0, 2], "denominator": 20}
}
```

`name` identifies the runtime value; `api_name` is the native SamplingParams keyword. Only `stage: completion` is implemented. Every entry in the list participates; remove an entry to omit it. `initial` starts each experiment, and `null` is a value state rather than exclusion. The file is never rewritten during generation. Bounds are project limits. `control.window` and `control.denominator` define the numeric candidate step; `control.adaptive: false` keeps a field fixed while still passing its initial value. The old per-entry `enabled` flag is rejected.

On load, `initial_parameters` takes each listed entry's `name` and `initial` to build one plain runtime map. For example, entries for `temperature`, `ignore_eos`, and `logprobs` produce `{"temperature": 0.6, "ignore_eos": false, "logprobs": null}`; the real map contains all 20 listed entries. Types, descriptions, bounds, and `control` remain in the definitions for validation and later Jev Choices; they do not become nested runtime values. The map is held in `sampling` in memory, then copied into each experiment's starting parameters. Each round records the parameters actually applied in `result.json`.

`control` is required by the current parser even when it is empty. Write `"control": {}` for booleans such as `ignore_eos` and enums such as `output_kind`: their `type`, current value, and declared `choices` already determine the available actions. An empty object does **not** freeze the parameter. To hold any parameter at its initial value while still passing it to vLLM, use `"control": {"adaptive": false}`. Numeric entries need `window` and `denominator`; nullable numeric entries additionally need `enable_candidates`; lists and maps need reviewed `candidates` or `entries` before they can gain new items.

The supplied 20 examples cover numeric, boolean, nullable list/map, enum, and nullable integer values. At their initial values, 17 produce an actionable direction Choice and three token-ID controls (`stop_token_ids`, `allowed_token_ids`, `logit_bias`) remain hold-only until reviewed candidates are supplied. Numeric controls offer keep/increase/decrease, then one to three exact values. Nullable integers first choose whether to enable from reviewed starting values; once numeric, they use the same bounded step rule and can also return to `null`. Booleans offer keep or the opposite state; enums switch among declared `choices`. The output-representation and log-probability fields can be changed as interface experiments, but their changes must not be interpreted as answer-quality improvements. No remaining-token budget is sent to Jev.

The old `adjustments` triggers are no longer accepted. Add a parameter by selecting a native SamplingParams field, declaring its type, and supplying type-appropriate `control` metadata. The installed vLLM and the segmented runner still validate the result.

The current selection is `temperature`, `top_p`, `top_k`, `repetition_penalty`, `frequency_penalty`, `presence_penalty`, `min_p`, `ignore_eos`, `stop_token_ids`, `allowed_token_ids`, `logit_bias`, `output_kind`, `logprobs`, `prompt_logprobs`, `min_tokens`, `detokenize`, `skip_special_tokens`, `spaces_between_special_tokens`, `include_stop_str_in_output`, and `flat_logprobs`. The three token-ID candidate sets are empty by default. The runner owns seed, max_tokens, and single-candidate generation. After an interrupted batch, `python run.py compare --start-task TASK_ID` starts again at that dataset task; it does not resume an incomplete task or overwrite prior result directories. Transient HTTP 5xx responses from Jev are retried up to twice before the run stops.

Representative examples for each selected type, including fixed observation fields and reviewed-candidate rules: [parameter examples](docs/parameter_examples.md). The [strict example JSON](docs/parameter_examples.json) mirrors the active selection without comments.

For the broader vLLM design space, see the [1,181-entry checklist taxonomy](docs/vllm_catalog_taxonomy.md) and its [row-by-row CSV](docs/vllm_catalog_taxonomy.csv). This inventory separates current Python controls from other routes and does not certify runtime support.

### Evaluation rubrics and task data

`jev_questions.json` defines correctness, relevance, repetition and completeness. Each uses `type: score`, English `instructions`, and an ordered `criteria` list. The current five levels correspond to 0–4. Parsing validates score and probability distribution; normalization divides score by 4. High repetition is undesirable; the other dimensions reward higher scores.

Tasks belong in `data/tasks.jsonl`, not in the rubric file. JSONL is strict JSON: one complete object per line, no comments or outer array:

```jsonl
{"id":"example_001","prompt":"Solve 2x + 3 = 11.","reference_answer":"4"}
```

Unique nonempty `id` and `prompt` are required. Reference fields are optional metadata and are not sent to Qwen/Jev. The included development sample contains ten original English GSM8K **training** questions sampled without replacement using seed 42; provenance is in `data/gsm8k_sample_manifest.json`. It is not a full held-out benchmark. No automatic reference-answer grader is implemented.

## 4. Call flow and decision rules

| Module | Responsibility |
|---|---|
| run.py / cli.py | Parse commands, select modes, construct shared clients and iterate tasks/seeds |
| config.py | Strip comments, resolve paths, load definitions/rubrics and validate configuration |
| parameters.py / value_schema.py | Validate definitions and map names to native keywords |
| backend.py | Keep one LLM loaded, tokenize, generate and decode |
| runner.py | Segment loop, budgets, evaluation calls and incremental records |
| jev_requests.py | Build typed Score, direction Choice and exact-value Choice JSON requests |
| adapters.py | Validate scores and remove unused response metadata |
| clients.py | Authenticated HTTPS request to Jev |
| policy.py | Score stopping, cooldown, rollback and accepted-choice commit |

For one task, seed, and mode, the flow is:

1. **Load definitions and initial values.** `config.load_config` loads `parameters.json` and `jev_questions.json`. `parameters.initial_parameters` maps every listed `name` to its `initial` value, producing one plain in-memory `sampling` map; definitions such as `type`, `description`, bounds, and `control` remain available separately. The map is copied at the start of each run. It is not written as a standalone file, and the original `initial` values are not changed by later decisions.
2. **Generate the first segment with vLLM.** `runner.execute` applies the model's chat template to the task's `prompt`, yielding prompt token IDs; `add_generation_prompt` adds the assistant-start marker, not another question. Each generation request contains those token IDs plus all previously generated IDs, the current parameter map translated from `name` to native `api_name`, a segment `max_tokens` limited by the remaining budgets, and `seed + step`. Before generation, `result.json` records `rounds[].applied_parameters` and `generation_request`; after success, it records `generation_response` and timing. Jev has not changed any parameters before the first segment.
3. **Score the new text.** The new token IDs extend the cumulative output. `jev_requests.score_request` sends the four rubrics with `state={task, generated, recent, step}`. Neither the reference answer nor the remaining token budget is sent. `evaluation_request` is saved before the Jev call; `evaluation_response` and elapsed time are saved after it. `adapters.parse_scores` requires a finite score within the rubric range and probabilities for every level that sum to 1 within 0.02. It then maps each raw 0–4 score to `normalized = score / 4` under the current five-level rubrics. The probabilities are retained and validated, but the controller uses the normalized scores rather than a separate confidence value. The parsed values appear in `rounds[].scores`.
4. **Decide whether a parameter Choice is allowed.** `policy.Controller.decide` combines the four normalized scores into `utility`, reversing repetition so that less repetition is better. Fixed mode holds the parameters. Adaptive mode first checks feedback from the last change for rollback, then optional score stopping and cooldown. The runner also checks model stop and token, context, round, and Jev-call budgets. Only a continuing round with `reason: choice_ready` proceeds to parameter Choice. This local decision does not itself alter the current segment.
5. **Ask for directions.** `jev_requests.direction_request` reads each definition's type and current value to generate feasible operations: for example, `temperature=0.6` offers keep/increase/decrease, `ignore_eos=false` offers keep/turn_on, and `logprobs=null` offers keep/enable. A parameter with only keep is omitted as a question. With the current definitions and initial values, 17 of 20 parameters get questions; the other three token-ID controls lack reviewed candidates. All direction questions share one Jev request whose state includes the task, text, four normalized scores, and the full current parameter map. Each question also includes the parameter's `description` and current value. The request and answer are saved as `direction_request` and `direction_response`. This is one Choice question per eligible parameter; the implementation does not jointly optimize the complete combination of changes.
6. **Map directions to exact values.** A chosen keep produces no change. A single-result action such as `turn_on` maps directly to `true`. For a numeric increase or decrease, `jev_requests.value_candidates` computes one-, two-, and three-step values from `control.window` and `control.denominator`, discarding values outside the window or hard bounds. Thus `temperature=0.6`, window `[0,2]`, denominator `20`, and increase yield `0.7`, `0.8`, `0.9`; `top_k=20` with `[1,101]` and denominator `20` yields `25`, `30`, `35`. Enabling nullable `logprobs` offers the declared starting values `0`, `1`, `2`; after it has a number, it uses bounded steps. Parameters with multiple exact candidates are grouped into one further Jev request, logged as `value_request`, `value_response`, and `value_seconds`. The answer's `v1`/`v2`/`v3` keys are mapped back to actual values. This request carries the current map and each question's own chosen direction, but does not summarize other parameters' selected directions in shared state.
7. **Commit for the next segment.** `Controller.commit` copies the full current map and overlays the chosen `changes`. With no effective changes it holds; otherwise `rounds[].decision` records `action: adjust`, the complete proposed next map, and the pre-change utility used for later feedback. The runner copies that map into `params` for the next loop iteration. `decision_will_execute: true` means continuation is planned, not that generation succeeded. Only the next round's `applied_parameters` and `generation_request` show values submitted to vLLM; its `generation_response` confirms that call completed. A budget check can still stop the run before that next request.
8. **Save answers and evaluate the change.** `result.json` is updated throughout the run; `rounds[].answer_snapshot` and the labeled sections in `answer.txt` preserve the cumulative answer after each generated segment. The last section is the final full answer. After the next segment is scored, the controller compares its utility with the pre-change utility. A drop beyond `policy.rollback.score_drop` proposes restoring the old parameter map for a later segment; it cannot undo text already generated. There are no automatic low-correctness or high-repetition adjustment triggers.

Early stopping remains under `policy.stopping`: `enabled: false`, `completeness_min: 1.0`, `correctness_min: 0.75`, and `relevance_min: 0.75`. All three normalized minimums must be met when enabled. Activate the required Python environment; no interpreter path or backend selector belongs in the configuration.

Composite quality is on a 0-1 scale. With the current five-level rubrics and default weights: `0.45*(correctness/4) + 0.30*(relevance/4) + 0.15*(completeness/4) + 0.10*(1-repetition/4)`. All `utility_weights` are nonnegative (0-1), with at least one positive; code divides by their sum. Other rubric sizes use their own maximum for normalization. `policy.rollback.score_drop: 0.15` restores the previous parameters when quality drops by more than 0.15 points after an adjustment, not by 15%. This preserves the previous default rollback sensitivity. Rollback does not erase generated text or prove causality. Historical output utility values use the old scale and must not be directly compared with new values.

## 5. Run modes

Run these commands yourself from the directory containing `run.py`:

| Command | Effect | Loads GPU model | Calls Jev |
|---|---|---|---|
| `python run.py check` | Validate configuration and task loading | No | No |
| `python run.py preview` | Print illustrative Score/direction/value JSON | No | No |
| `python run.py doctor` | Construct native SamplingParams | No | No |
| `python run.py smoke` | Generate eight tokens for the first task | Yes | No |
| `python run.py run` | Run the configured fixed/adaptive mode | Yes | Yes |
| `python run.py compare` | Run fixed then adaptive for each task/seed | Yes | Yes |
| `python run.py summarize` | List saved experiment summaries | No | No |

An alternate configuration is selected with `python run.py run --config "E:\Experiments\config.json"`; copy its referenced files or update their paths too.

For an adaptive experiment set `experiment.mode` to `adaptive`; for a fixed experiment set it to `fixed`. `compare` chooses both automatically and disables score-based early stopping in both. Both groups still call Jev. A continuous, no-Jev baseline is not implemented.

For each task and seed, fixed mode uses at most one Jev Score request per round; adaptive uses at most three requests (Score, direction Choice, exact-value Choice). Each run is also capped by `max_jev_calls`. With 10 tasks, one seed and eight rounds, fixed ≤80 requests, adaptive ≤240, compare ≤320. Model stopping or choosing keep reduces the actual count.

### Command recipes

Run each command from the repository root with the environment active. Checks do not start an experiment automatically.

**check — validate configuration and task input**

```shell
python run.py check
```

Expected console output begins with `Configuration valid; tasks=...; backend=python; mode=...`. It reads the configuration, parameter definitions, rubrics and task file. It does not load the model, authenticate the key or spend Jev credits.

**preview — inspect the three Jev JSON request shapes offline**

```shell
python run.py preview
```

This prints illustrative Score, direction Choice, and exact-value Choice payloads. It does not load Qwen or call Jev.

**doctor — validate the native parameter interface**

```shell
python run.py doctor
```

Expected output: `Native SamplingParams validated. No model loaded and no Jev call made.` It imports vLLM and constructs SamplingParams with the selected values, but does not verify GPU inference or all possible future parameter combinations.

**smoke — one short local generation**

```shell
python run.py smoke
```

This loads Qwen and generates at most eight tokens for the first task, printing response JSON to the terminal. It makes no Jev request and does not create the normal experiment result folder. A short fragment is expected; this is not an answer-quality test.

**run — one configured experiment mode**

```shell
python run.py run
```

This runs every task and seed using `experiment.mode`, makes Jev calls, and creates a result folder for each task/seed. Use one of the fixed/adaptive recipes below.

**compare — two modes per task and seed**

```shell
python run.py compare
```

The command overrides the configured mode, runs fixed then adaptive for each task/seed, and turns off score-based stopping in both. It produces separate result folders, not a statistical comparison report. Both groups call Jev; inference and evaluator costs can therefore roughly double relative to one mode, subject to actual stopping.

**summarize — inspect existing records**

```shell
python run.py summarize
```

Prints one JSON summary per result: task, seed, mode, status, stop reason, generated-token count, Jev-call count, elapsed seconds and file path. It makes no API/model call. It still loads the current configuration and tasks, so those files must remain valid. It searches immediate result subdirectories of the configured outputs directory; it does not grade answers.

### Fixed / adaptive / compare: choose an experiment

The following fragments replace the existing `experiment` object in `config.json`; keep all other sections.

**A. Fixed parameters, with Jev observation**

```json
"experiment": {
  "mode": "fixed",
  "seeds": [42],
  "max_jev_calls": 8
}
```

```shell
python run.py run
```

Each segment is evaluated, but parameters remain at their initial values. Expect folders ending in `_fixed`; decisions hold with `fixed_parameter_control`. With ten tasks and a maximum of eight rounds, at most 80 evaluator requests are made.

**B. Adaptive parameters from Jev feedback**

```json
"experiment": {
  "mode": "adaptive",
  "seeds": [42],
  "max_jev_calls": 8
}
```

```shell
python run.py run
```

Expect `_adaptive` folders. Decisions may hold, adjust or roll back; enabled score-based stopping can also stop generation. Holding parameters is a valid outcome, not proof that Jev was unused. The ten-task/eight-round upper bound is 240 requests, subject to each run's `max_jev_calls`.

**C. Paired fixed/adaptive run**

Keep either fragment above; the command selects both modes:

```shell
python run.py compare
```

Ten tasks and one seed produce up to 20 experiment folders and at most 320 requests at eight rounds, subject to each run's `max_jev_calls`. Both groups share starting values and budgets. Score-based stopping is disabled, but EOS and budget limits still apply. Read each group's result.json and answer.txt; an independent reference-answer grader is still needed for accuracy comparison.

## 6. First run and results

1. Edit paths, direct API key and input tasks.
2. Run `check`, then `doctor`, then `smoke`.
3. Choose **one** of `run` and `compare` according to the experiment goal.
4. Run `summarize` and inspect the saved records.

From a configured checkout, a single-mode run is:

```powershell
conda activate jev-vllm
cd Jev-for-llm
python run.py run
```

For the two-group experiment, replace the last command with `python run.py compare`. No credential setup outside `config.json` is needed. `check` does not authenticate the API key; `doctor` validates parameter construction but does not prove the model or every parameter combination will run.

Each task/seed/mode creates `outputs/<timestamp>_<mode>/result.json` and `answer.txt`. `answer.txt` contains a labeled cumulative-answer snapshot after every generated round; the last snapshot is the final full answer. `result.json` also keeps each round's `answer_snapshot`. Inspect `rounds[].scores`, `decision`, `applied_parameters`, `generation_request`, timing and stop reason. A proposed adjustment is only confirmed by the next round's actual request. `decision_will_execute` alone does not prove the next call succeeded.

Normal completion means the loop ended, not that the answer is correct. Stopping may be caused by the model, token/context/round/call budgets, or enabled score stopping. Ctrl+C normally records interruption; forced process termination can leave `status: running`. Partial records remain. Rerunning starts over; there is no resume or automatic paid retry. An exception stops the remaining experiment loop.

For a local log (after the key is configured):

```powershell
New-Item -ItemType Directory -Force outputs | Out-Null
python run.py compare 2>&1 | Tee-Object -FilePath outputs/compare.log
```

This PowerShell example saves a console log inside the configured checkout. Logs may contain task/model output. Results, not only console messages, are the experiment record.

## 7. Tests and troubleshooting

Optional developer-only check: if you also have the separate sibling test directory with the expected development layout, run:

```powershell
python -m unittest discover -s ../tests -v
```

These tests use fake model/evaluator objects. They do not consume API credits. A standalone checkout needs the separate test directory before this command is meaningful.

| Symptom | What to check |
|---|---|
| Key prompt still appears | An old process/code version is running. Stop it and relaunch the updated code; current authentication reads jev.api_key only. |
| HTTP 401/403 | Key validity and organization access |
| Billing/out-of-funds response | TypeSafe organization balance |
| Timeout/TLS error | Network, proxy and timeout settings; no automatic retry |
| Cannot import vllm | Selected Python environment and installed wheel |
| GPU out of memory | Other GPU jobs, context length and engine memory settings |
| min_tokens error after adding that field | It must fit the actual remaining segment budget; smoke only allocates eight tokens |
| Budget reached without final answer | Inspect thinking output and increase budgets deliberately if needed |

## 8. Interpretation limits and further reading

Each segment is a separate generate call; earlier tokens become prompt context. Presence/frequency penalties apply to newly generated tokens within that call, while repetition penalty also considers prompt tokens. Stop matching across segment boundaries is not guaranteed. Parameters change between calls, not during an active call. Prefix caching may help but does not make segmented generation identical to continuous generation.

Jev and each `answer.txt` snapshot use cumulative raw decoding, potentially including special tokens and stop content; display options affect native display text. Seed is incremented by segment index. Fixed/adaptive comparisons share starting values and budgets, but that does not guarantee identical random trajectories or improved accuracy.

See [implementation notes](docs/implementation.md), [Transformers migration](docs/transformers_to_vllm.md), and the [GSM8K source](https://github.com/openai/grade-school-math). Use an independent answer grader before making benchmark accuracy claims.
