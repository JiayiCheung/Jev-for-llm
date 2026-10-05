# Jev and vLLM Inference Control

**English** | [简体中文](docs/README.zh-CN.md) | [Website](https://jiayicheung.github.io/Jev-for-llm/)

Qwen generates text locally through the Python vLLM API. Jev rates each segment with Score rubrics that describe symptoms in the text. A configurable controller chooses the next segment's parameters. The model stays loaded throughout one process. Only Jev uses HTTPS; no local API server is required.

![Jev-guided segmented inference: generation, scoring, fixed and adaptive decisions, and the next-segment feedback loop](docs/figures/workflow_en.svg)

## Contents

- [Environment and installation](#1-environment-and-installation)
- [Layout and ownership](#2-layout-and-ownership)
- [File formats and configuration](#3-file-formats-and-configuration)
- [Run modes](#4-run-modes)
- [First run and results](#5-first-run-and-results)
- [Interpretation limits](#6-interpretation-limits-and-further-reading)

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

All commands below run from this repository root, where `run.py` is located. Update the paths in section 1.4 before running the project. If you already have a working vLLM environment, activate it and skip dependency reinstallation.

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

Activate your environment before running, or explicitly use its Python executable. Set `jev.api_key` in your local configuration or provide `TYPESAFE_API_KEY` in the process environment.

## 2. Layout and ownership

```text
Jev-for-llm/
  run.py                 Command-line entry point
  config.json            Paths, engine, API key and policy settings
  parameters.json        Selected native fields, types, defaults and actions
  jev_questions.json     Evaluator rubrics: symptom scores and an on_track forecast
  pyproject.toml         Package metadata and black / isort settings
  data/                  Active tasks and sampling provenance
  src/jev_vllm/          Implementation
  scripts/               Offline analysis and dashboard builders
  outputs/               Generated experiment records
  README.md              Project guide
```

Code style: [black](https://black.readthedocs.io/) and [isort](https://pycqa.github.io/isort/) with the settings in `pyproject.toml`, checked with `flake8` (using a local, untracked `.flake8`). Run `python -m black . && python -m isort . && python -m flake8` before committing.

## 3. File formats and configuration

| Section in config.json | Controls |
|---|---|
| paths | Model, dataset, output directory |
| engine | LLM constructor: dtype, context size, sequence capacity, GPU memory fraction, eager execution, tensor parallelism |
| runtime | Optional FlashInfer sampler switch |
| jev | HTTPS base URL, endpoint, model, direct API key, timeout, rubric file, request text view (how much generated text Choice requests carry) |
| generation | Thinking template switch (`enable_thinking`) and tokens per segment (`chunk_tokens`); a run has no other limit |
| parameters_file | Path to the selected parameter definitions |
| experiment | fixed/adaptive/baseline mode, seeds, `max_consecutive_errors` (failures in a row before a batch stops) |
| policy | restart from a checkpoint (Jev sends a long reasoning back), same-direction cap, dormancy of idle parameters, symptom weights, signal settings |

The project always uses the active Python interpreter and native vLLM. `engine` settings apply when constructing the model; selected SamplingParams apply to the next generation call.

### API key: configuration only

Within the existing `jev` object, set:

```json
"api_key": "YOUR_TYPESAFE_API_KEY"
```

The client uses `jev.api_key` when set, then falls back to `TYPESAFE_API_KEY`; it does not prompt for a key. Keep credentials out of published files. Saved experiment configuration redacts `api_key`.

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
  "minimum": 0.2,
  "maximum": 2,
  "description": "Sampling randomness",
  "control": {"window": [0.2, 2], "denominator": 18}
}
```

`parameters.json` sets each parameter's initial value and allowed adjustments. Jev selects type-appropriate changes between generation segments; the next segment uses the updated values. For supported types, field rules, and examples, see the [parameter guide](docs/parameter_examples.md) and [example JSON](docs/parameter_examples.json).

For the broader vLLM design space, see the [1,181-entry checklist taxonomy](docs/vllm_catalog_taxonomy.md) and its [row-by-row CSV](docs/vllm_catalog_taxonomy.csv). This inventory separates current Python controls from other routes and does not certify runtime support.

### Evaluation rubrics and task data

`jev_questions.json` defines the Score rubrics. Each uses `type: score`, a `kind`, English `instructions`, and an ordered `criteria` list; the five levels correspond to 0–4. The `kind` is read by the program and is never sent to Jev.

| Rubric | Kind | Scored on | Looks for |
|---|---|---|---|
| `scatter` | symptom | last segment | careless slips that look like sampling noise |
| `rigidity` | symptom | last segment | repeating itself, looping |
| `distortion` | symptom | last segment | garbled text, language switches, odd formats |
| `over_checking` | symptom | last three segments | re-checking or re-stating results that no longer change |
| `under_checking` | symptom | last three segments | concluding or switching approach without checking |
| `on_track` | forecast | whole reasoning | likelihood of a correct final answer (used only by the restart check) |

For a symptom, 0 means not present and 4 means severe, so a higher score is worse; for the forecast a higher score is better. The score request sends `task`, `segments` (the kept segments as one list, the newest last, so that no text appears twice) and a short `about` note; each rubric says which items of `segments` it judges.

The program computes, for every symptom, `severity` (expected level divided by the highest level) and `p_severe` (probability of the two highest levels). `trouble` is the largest weighted severity (`policy.symptom_weights`, scaled so the largest weight is 1) and `worst` names the symptom behind it. When Jev chooses parameters it sees these values together with the first segment's values (`at_start`), the last three segments, how many consecutive segments each symptom persisted (`policy.signals.persistence_threshold`), its own recent parameter changes and how long each change has been in effect, and a `reading_guide` that only explains the fields. Nothing in the request tells Jev what to do about a symptom, and each parameter description states mechanism, range and neutral value only. `trouble` is shown and recorded; no program rule acts on it.

Tasks belong in `data/tasks.jsonl`, not in the rubric file. JSONL is strict JSON: one complete object per line, no comments or outer array:

```jsonl
{"id":"example_001","prompt":"Solve 2x + 3 = 11.","reference_answer":"4"}
```

Unique nonempty `id` and `prompt` are required. Reference fields are optional metadata and are not sent to Qwen/Jev. The task sets are original English GSM8K **test** questions, all sampled without replacement with a fixed seed; `paths.dataset` selects one:

| File | Tasks | Use |
|---|---|---|
| `data/tasks.jsonl` | 400 | Default sample (`python scripts/prepare_gsm8k.py --split test --count 400 --seed 42`; add `--download` to fetch the raw file into the git-ignored `data/raw/`). Manifest: `data/gsm8k_sample_manifest.json` |
| `data/tasks_full.jsonl` | 1319 | The whole test set in a seed-42 random order, so any prefix is a uniform random subset and an interrupted batch still has an unbiased sample. Manifest: `data/gsm8k_full_manifest.json` |
| `data/tasks_heldout.jsonl` | 1199 | The full set without the 20 tasks seen while the scoring design was debugged and the 100 pilot tasks. Manifest: `data/tasks_heldout.manifest.json` |
| `data/tasks_pilot100.jsonl` | 100 | Pilot sample: 100 tasks drawn with seed 20261005 from the 400-task sample after excluding the 20 debugging tasks. Manifest: `data/tasks_pilot100.manifest.json` |
| `data/tasks_train10.jsonl` | 10 | Ten training-set questions for quick smoke tests. Manifest: `data/tasks_train10.manifest.json` |

Provenance and the SHA256 of the source file are in the manifests. Answers are graded offline by `scripts/analyze_results.py`; the grader is not used while generating. It reads the last `oxed{}` (or a `####` / `Answer:` line that holds just a number), strips markup around the number, evaluates plain arithmetic and exact fractions, and compares exactly. A final box that holds no readable number is graded incorrect; output with no explicit answer is left ungraded. The full rules, and the convention for flagging suspect reference labels, are in [result analysis](docs/analysis.md).

### Restarting from a checkpoint

Restart lets Jev send a long reasoning back instead of only adjusting parameters. It is used in adaptive mode only; fixed mode scores and never intervenes, so it stays a clean control. It is controlled by `policy.restart`:

1. From round `first_check_round`, and then every `recheck_every` rounds after a *continue*, Jev answers one Choice request: continue, go back to the very start, or go back to an earlier checkpoint. A checkpoint is a point where Jev was asked and said continue; its `on_track` score is shown with it.
2. After a choice to go back, the run rewinds to that point and generates a fresh attempt of `probe_rounds` segments with a new seed.
3. Jev is then asked whether the fresh attempt takes a different approach from the abandoned one. If it does, the run continues from it; if not, the attempt is discarded and another is generated, up to `max_tries` attempts.
4. A run stops asking after `max_restarts` restarts. There is no token cap, so a restarted run can cost noticeably more tokens.

Every restart is saved in `result.json` under `restarts` (the point chosen, each attempt's verdict, and how it ended), and abandoned rounds stay in the record marked `abandoned`.

## 4. Run modes

Run these commands yourself from the directory containing `run.py`:

| Command | Effect | Loads GPU model | Calls Jev |
|---|---|---|---|
| `python run.py check` | Validate configuration and task loading | No | No |
| `python run.py preview` | Print illustrative Score/direction/value JSON | No | No |
| `python run.py doctor` | Construct native SamplingParams | No | No |
| `python run.py smoke` | Generate eight tokens for the first task | Yes | No |
| `python run.py run` | Run the configured fixed/adaptive mode | Yes | Yes |
| `python run.py run --mode baseline` | Generate with fixed parameters and no Jev requests | Yes | No |
| `python run.py compare` | Run fixed then adaptive for each task/seed | Yes | Yes |
| `python run.py summarize` | List saved experiment summaries | No | No |
| `python run.py dashboard` | Open an interactive visualization of experiment results | No | No |

An alternate configuration is selected with `python run.py run --config "E:\Experiments\config.json"`; copy its referenced files or update their paths too.

For an adaptive experiment set `experiment.mode` to `adaptive`; for a fixed experiment set it to `fixed`. `compare` chooses both automatically. Both groups still call Jev. Use `run --mode baseline` for a separate no-Jev reference run; [result analysis](docs/analysis.md) explains how to match it to an adaptive batch.

For each task and seed, fixed mode uses at most one Jev Score request per round; adaptive uses at most three requests per round (Score, direction Choice, exact-value Choice). Adaptive mode adds one checkpoint Choice request at each restart check and, after a restart, one comparison request per fresh attempt. There is no cap on rounds or requests: a run ends when the model stops or the context window is full, so the request count grows with how long the model keeps reasoning.

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

The command overrides the configured mode, runs fixed then adaptive for each task/seed. It produces separate result folders, not a statistical comparison report. Both groups call Jev; inference and evaluator costs can therefore roughly double relative to one mode, subject to actual stopping.

**summarize — inspect existing records**

```shell
python run.py summarize
```

Prints one JSON summary per result: task, seed, mode, status, stop reason, generated-token count, Jev-call count, elapsed seconds and file path. It makes no API/model call. It still loads the current configuration and tasks, so those files must remain valid. It searches immediate result subdirectories of the configured outputs directory; it does not grade answers.

**dashboard — visualize experiment results**

```shell
python run.py dashboard
```

Opens an interactive dashboard of saved experiment results, laid out like TensorBoard: a tab bar, a settings column (batch, control, answer filter, task search, which runs to draw, curve smoothing) and cards that each hold one chart or table with SVG and CSV download. The six tabs are Overview (accuracy against tokens with 95% intervals, paired scatterplots, the paired 2×2 table with the exact McNemar test, cost breakdown), Curves (every per-segment quantity), Distributions, Judge (`on_track` calibration and AUC, symptom trigger rates), Behavior (direction and timing of parameter changes, restarts) and Tasks (per-task lines and a sortable table with a detail drawer). It needs no GPU. Use `--no-browser` to print the URL only and `--port N` to pick a port. [Result analysis](docs/analysis.md) describes each tab.

## 5. First run and results

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

For the two-group experiment, replace the last command with `python run.py compare`. `check` does not authenticate the API key; `doctor` validates parameter construction but does not prove the model or every parameter combination will run.

Each task/seed/mode creates `outputs/<timestamp>_<mode>/result.json` and `answer.txt`. `answer.txt` contains a labeled cumulative-answer snapshot after every generated round; the last snapshot is the final full answer. `result.json` also keeps each round's `answer_snapshot`. Inspect `rounds[].scores`, `decision`, `applied_parameters`, `generation_request`, timing and stop reason. A proposed adjustment is only confirmed by the next round's actual request. `decision_will_execute` alone does not prove the next call succeeded.

Normal completion means the loop ended, not that the answer is correct. A run ends when the model stops or the context window is full (`stop_reason` `model_stop` or `context_budget`). Ctrl+C normally records interruption; forced process termination can leave `status: running`. Partial records remain.

**Long batches and resuming.** Every `run`/`compare` prints its experiment ID and a progress line after each finished run (`[done/total] … about 2h15m left at this pace`). The unit of resumption is one run (one task, one seed, one mode, about one to a few minutes, rarely longer): after an interruption — Ctrl+C, a closed window, a power cut, a network outage — run the same command with the same configuration and add `--resume` (for example `python run.py compare --resume`): the most recent batch with exactly this plan is continued and its ID is printed; add `--experiment-id <id>` to pick a specific one. Runs whose `result.json` says `completed` are skipped; an unfinished or broken record is ignored and that run starts again from its first segment (the old folder stays on disk as an audit trail and is left out of the analysis). A changed task list, seed list, mode list or experimental condition is refused, so a batch can never mix two plans; keep `--task` and `--start-task` out of a resumed command for the same reason. Jev calls retry transient HTTP and network errors with the waits in `jev.retry_delays`. A run that still fails is recorded with status `error`, reported, and skipped so the batch keeps going; after `experiment.max_consecutive_errors` failures in a row the batch stops (something shared is probably gone), the exit code is 1, and the same `--resume` command retries exactly what is missing.

For a local log (after the key is configured):

```powershell
New-Item -ItemType Directory -Force outputs | Out-Null
python run.py compare 2>&1 | Tee-Object -FilePath outputs/compare.log
```

This PowerShell example saves a console log inside the configured checkout. Logs may contain task/model output. Results, not only console messages, are the experiment record.

## 6. Interpretation limits and further reading

Each segment is a separate generate call; earlier tokens become prompt context. Presence/frequency penalties apply to newly generated tokens within that call, while repetition penalty also considers prompt tokens. Stop matching across segment boundaries is not guaranteed. Parameters change between calls, not during an active call. Prefix caching may help but does not make segmented generation identical to continuous generation.

Jev and each `answer.txt` snapshot use cumulative raw decoding, potentially including special tokens and stop content; display options affect native display text. Seed is incremented by segment index. Fixed/adaptive comparisons share starting values and budgets, but that does not guarantee identical random trajectories or improved accuracy.

See [implementation notes](docs/implementation.md) and the [GSM8K source](https://github.com/openai/grade-school-math). Use an independent answer grader before making benchmark accuracy claims.
