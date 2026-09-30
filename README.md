# Jev and vLLM Inference Control

**English** | [简体中文](README.zh-CN.md)

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

Choose **one** platform route. This project does not bundle model weights or install vLLM through its package metadata.

**Linux / WSL2 with NVIDIA GPU:** inside the Linux environment, install the upstream wheel and its matching dependencies:

```shell
python -m pip install vllm
python -m pip check
```

This is the upstream default-wheel route, not an environment lock. Check the [official GPU installation requirements](https://docs.vllm.ai/en/latest/getting_started/installation/gpu/) against your Python, GPU and driver before installation. A different CUDA/PyTorch combination may need a different upstream build. WSL commands run inside Linux, not in a Windows Conda environment.

**Native Windows:** use the [Windows community build instructions](https://github.com/SystemPanic/vllm-windows#installing-an-existing-release-wheel), select a [release wheel](https://github.com/SystemPanic/vllm-windows/releases) matching its stated Python, PyTorch and CUDA requirements, and download it. Then replace the example filename with the actual downloaded file:

```powershell
python -m pip install "C:/Downloads/ACTUAL_RELEASE_WHEEL.whl"
python -m pip check
```

The filename is a placeholder, not a release artifact. There is no single wheel command suitable for every Windows environment. The project was exercised with Python 3.12 and a Windows vLLM 0.29.0 build; a fresh installation must be checked independently.

For either route, verify the selected interpreter and GPU visibility:

```shell
python -c "import sys, torch, vllm; print(sys.executable); print(vllm.__version__); print(torch.__version__); print(torch.version.cuda); print(torch.cuda.is_available())"
```

The last line should be `True`. This checks GPU visibility, not successful model inference.

### 1.3 Install this project and download model files

```shell
python -m pip install -e .
python -m pip install huggingface_hub
hf download Qwen/Qwen3-0.6B --local-dir models/Qwen3-0.6B
```

The [Hugging Face CLI](https://huggingface.co/docs/huggingface_hub/guides/cli) downloads weights, tokenizer and configuration files. If a complete local model already exists, skip the download and use that directory. `pyproject.toml` describes this Python package; it is not a lockfile for GPU dependencies. Editable installation makes the package importable; `run.py` also supports execution directly from the checkout.

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

NVIDIA drivers, PyTorch CUDA runtime and CUDA Toolkit are different layers. Optional JIT kernels can additionally need Toolkit and a compatible compiler. Keep `runtime.use_flashinfer_sampler` false for the first run. Windows JIT compilation may need a correctly initialized MSVC developer terminal; installing the VS Code C/C++ extension does not install `cl.exe`.

## 2. Layout and ownership

```text
Jev-for-llm/
  run.py                 Command-line entry point
  config.json            Paths, engine, budgets, API key and policy thresholds
  parameters.json        Selected native fields, types, defaults and actions
  jev_questions.json     Four evaluator rubrics
  pyproject.toml         Package/build metadata; not a GPU environment lockfile
  data/                  Active tasks and sampling provenance
  docs/                  Implementation and migration notes
  src/jev_vllm/          Implementation
  outputs/               Generated experiment records
  README.md              English guide
  README.zh-CN.md         Chinese guide
```

The development workspace also has sibling `../tests`, `../scripts` and `../data` directories for controller tests, helper scripts/logs and raw downloads. They are outside this repository and are not a prerequisite for normal runs. A standalone clone may not contain them; its active dataset is the repository-local `data/tasks.jsonl`. Native vLLM interface tests are maintained separately.

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
  "enabled": true,
  "type": "number",
  "initial": 0.6,
  "minimum": 0,
  "maximum": 2,
  "adjustments": {
    "narrow_sampling": {"op": "add", "value": -0.1}
  }
}
```

`name` identifies the runtime value; `api_name` is the native SamplingParams keyword. Only `stage: completion` is implemented. `initial` starts each experiment; the definition file is not rewritten during generation. Bounds are project limits, not a claim about the full native domain. `enabled: false` omits that override; empty `adjustments` keeps it fixed.

Supported types: number, integer, boolean, string, array, object, null, and unions expressed as a type list. Arrays support `items`; objects support `properties`, `required`, and `additional_properties`. Actions are `add`, `set`, `append`, `remove`, and shallow `update`. `append`/`remove` require a current array, and `update` requires a current object; use `set` first for null values. Numeric additions clamp to configured bounds.

The two implemented trigger names are `narrow_sampling` and `reduce_repetition`. New trigger names require policy and validation changes; they cannot be added through the definition file alone.

| Group | Twenty selected native fields |
|---|---|
| Sampling | temperature, top_p, top_k, min_p |
| Penalties | repetition_penalty, presence_penalty, frequency_penalty |
| Termination | stop, stop_token_ids, ignore_eos, min_tokens |
| Observation | logprobs, prompt_logprobs |
| Display | detokenize, skip_special_tokens, spaces_between_special_tokens, include_stop_str_in_output |
| Restrictions | bad_words, allowed_token_ids, logit_bias |

The shipped definitions use the following values. These are the project's selected limits; the installed vLLM also validates native constraints and combinations.

| Parameter | Type | Initial value | Project limits / meaning |
|---|---|---|---|
| temperature | number | 0.6 | 0–2; 0 selects greedy decoding |
| top_p | number | 0.95 | 0.01–1 |
| top_k | integer | 20 | −1–1,000,000; native validation decides valid values |
| repetition_penalty | number | 1 | 1–1.5 |
| min_p | number | 0 | 0–1 |
| presence_penalty | number | 0 | −2–2 |
| frequency_penalty | number | 0 | −2–2 |
| stop | string / array / null | null | String or list of strings |
| stop_token_ids | array / null | null | Nonnegative integer token IDs |
| ignore_eos | boolean | false | Whether to ignore EOS |
| min_tokens | integer | 0 | 0–1024; also must fit each actual segment budget |
| logprobs | integer / null | null | 0–20; null disables collection |
| prompt_logprobs | integer / null | null | 0–20; null disables collection |
| detokenize | boolean | true | Native display text |
| skip_special_tokens | boolean | true | Native display text |
| spaces_between_special_tokens | boolean | true | Native display text |
| include_stop_str_in_output | boolean | false | Native display text |
| bad_words | array / null | null | List of strings |
| allowed_token_ids | array / null | null | Nonnegative IDs; use null rather than an empty allowlist |
| logit_bias | object / null | null | Token-ID string keys, numeric offsets −100–100 |

Currently only temperature, top_p and repetition_penalty have automatic actions. Additional fields must be supported by the installed SamplingParams and this segmented workflow; adding a name does not implement a new adapter. The runner owns seed, max_tokens and single-candidate generation.

Full worked examples for **every supported type and operation**, including fixed and disabled entries: [parameter examples](docs/parameter_examples.md). The [complete example JSON](docs/parameter_examples.json) is separate from the active configuration.

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
| parameters.py / value_schema.py | Build initial values, validate types/actions and map names to native keywords |
| backend.py | Keep one LLM loaded, tokenize, generate and decode |
| runner.py | Segment loop, budgets, evaluation calls and incremental records |
| adapters.py | Build Jev state; validate and normalize responses |
| clients.py | Authenticated HTTPS request to Jev |
| policy.py | trigger selection, cooldown and rollback |

`build_evaluation` sends `model`, `questions`, and `state`. State contains `task`, cumulative `generated` text, the `recent` segment, and zero-based `step`. It does not send reference answers. `parse_scores` requires a Score answer for every rubric, a finite score in the rubric's range, all probability-level keys, and probability sum within 0.02 of 1. With five criteria, a raw score of 3 becomes 0.75.


Decision order: fixed mode holds; pending feedback may roll parameters back; optional score stopping is checked; cooldown holds; then correctness at or below `correctness_max` or relevance at or below `relevance_max` reduces temperature by 0.1 and top_p by 0.05. Otherwise repetition at or above `repetition_min` increases repetition_penalty by 0.05.

Enter raw scores directly: the current `config.json` sets `policy.correctness_max: 2.0`, `policy.relevance_max: 2.0`, and `policy.repetition_min: 2.5`. Each accepts 0-4 with the current rubrics. Early stopping is grouped under `policy.stopping`: `enabled: false`, `completeness_min: 4.0`, `correctness_min: 3.0`, and `relevance_min: 3.0`. All three minimums must be met when enabled. Validation follows each rubric maximum. Activate the required Python environment; no interpreter path or backend selector belongs in the configuration.

Composite quality is on a fixed 0-4 scale. With the current five-level rubrics and default weights: `0.45*correctness + 0.30*relevance + 0.15*completeness + 0.10*(4-repetition)`. All `utility_weights` are nonnegative (0-1), with at least one positive; code divides by their sum. For other rubric sizes, scores are scaled internally. `policy.rollback.score_drop: 0.6` restores the previous parameters when quality drops by more than 0.6 points after an adjustment, not by 60%. This preserves the previous default rollback sensitivity. Rollback does not erase generated text or prove causality. Historical output utility values use the old scale and must not be directly compared with new values.

## 5. Run modes

Run these commands yourself from the directory containing `run.py`:

| Command | Effect | Loads GPU model | Calls Jev |
|---|---|---|---|
| `python run.py check` | Validate configuration and task loading | No | No |
| `python run.py doctor` | Construct native SamplingParams | No | No |
| `python run.py smoke` | Generate eight tokens for the first task | Yes | No |
| `python run.py run` | Run the configured fixed/adaptive mode | Yes | Yes |
| `python run.py compare` | Run fixed then adaptive for each task/seed | Yes | Yes |
| `python run.py summarize` | List saved experiment summaries | No | No |

An alternate configuration is selected with `python run.py run --config "E:\Experiments\config.json"`; copy its referenced files or update their paths too.

For an adaptive experiment set `experiment.mode` to `adaptive`; for a fixed experiment set it to `fixed`. `compare` chooses both automatically and disables score-based early stopping in both. Both groups still call Jev. A continuous, no-Jev baseline is not implemented.

The request upper bound is `tasks × seeds × modes × min(max_rounds, max_jev_calls)`. With 10 tasks, one seed and eight rounds: run ≤80 requests, compare ≤160; each request contains four scoring questions. This is a request count, not a price quote. Earlier stopping can reduce it.

### Command recipes

Run each command from the repository root with the environment active. Checks do not start an experiment automatically.

**check — validate configuration and task input**

```shell
python run.py check
```

Expected console output begins with `Configuration valid; tasks=...; backend=python; mode=...`. It reads the configuration, parameter definitions, rubrics and task file. It does not load the model, authenticate the key or spend Jev credits.

**doctor — validate the native parameter interface**

```shell
python run.py doctor
```

Expected output: `Native SamplingParams validated. No model loaded and no Jev call made.` It imports vLLM and constructs SamplingParams with the selected values, but does not verify GPU inference or all possible future parameter combinations.

**smoke — one short local generation**

```shell
python run.py smoke
```

This loads Qwen and generates at most eight tokens for the first task, printing response JSON to the terminal. It makes no Jev request and does not create the normal experiment result folder. A short fragment is expected; this is not an answer-quality test. The configured min_tokens must fit the eight-token budget.

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

Expect `_adaptive` folders. Decisions may hold, adjust or roll back; enabled score-based stopping can also stop generation. Holding parameters is a valid outcome, not proof that Jev was unused. The same ten-task/eight-round upper bound is 80 requests.

**C. Paired fixed/adaptive run**

Keep either fragment above; the command selects both modes:

```shell
python run.py compare
```

Ten tasks and one seed produce up to 20 experiment folders and at most 160 requests at eight rounds. Both groups share starting parameter values and budgets. Score-based stopping is disabled, but EOS and budget limits still apply, so their actual lengths can differ. Read each group's result.json and answer.txt; an independent reference-answer grader is still needed for accuracy comparison.

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

Each task/seed/mode creates `outputs/<timestamp>_<mode>/result.json` and `answer.txt`. Inspect `rounds[].scores`, `decision`, `applied_parameters`, `generation_request`, timing and stop reason. A proposed adjustment is only confirmed by the next round's actual request. `decision_will_execute` alone does not prove the next call succeeded.

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
| cl.exe not found | MSVC developer environment for optional JIT compilation |
| GPU out of memory | Other GPU jobs, context length and engine memory settings |
| min_tokens error | It must fit the actual remaining segment budget; smoke only allocates eight tokens |
| Budget reached without final answer | Inspect thinking output and increase budgets deliberately if needed |

## 8. Interpretation limits and further reading

Each segment is a separate generate call; earlier tokens become prompt context. Presence/frequency penalties apply to newly generated tokens within that call, while repetition penalty also considers prompt tokens. Stop matching across segment boundaries is not guaranteed. Parameters change between calls, not during an active call. Prefix caching may help but does not make segmented generation identical to continuous generation.

Jev and `answer.txt` use cumulative raw decoding, potentially including special tokens and stop content; display options affect native display text. Seed is incremented by segment index. Fixed/adaptive comparisons share starting values and budgets, but that does not guarantee identical random trajectories or improved accuracy.

See [implementation notes](docs/implementation.md), [Transformers migration](docs/transformers_to_vllm.md), and the [GSM8K source](https://github.com/openai/grade-school-math). Use an independent answer grader before making benchmark accuracy claims.
