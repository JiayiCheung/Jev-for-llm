# Result analysis

`scripts/analyze_results.py` builds an incremental local index of `result.json` files and exports `runs.csv`, `pairs.csv`, `issues.csv`, and `summary.json`. It uses only the Python standard library. The index and reports belong under `outputs/`, which is ignored by Git.

```powershell
python run.py compare --experiment-id pilot-001
python scripts/analyze_results.py --outputs outputs --report-dir outputs/analysis/pilot-001 --experiment-id pilot-001
python scripts/plot_performance.py --report-dir outputs/analysis/pilot-001 --output-prefix outputs/analysis/pilot-001/performance
```

For a new batch, omit `--experiment-id` and retain the ID printed by `run.py`; a manifest is saved in `outputs/experiments/<id>.json`. After an interruption, use the same ID with `--resume` and the same tasks/configuration. Completed task/seed/mode runs are skipped; interrupted or errored runs restart from their first segment. A changed plan is rejected. A `compare` batch contains only fixed and adaptive modes; both call Jev for Score. It is not a no-Jev baseline.

The exports have three levels:

| File | Unit | Key evidence |
|---|---|---|
| `runs.csv` | One saved run | Batch, task, seed, mode, status, stop reason, independent answer grade, generated tokens, Jev calls and token usage, timing, executed parameter changes, source path |
| `pairs.csv` | One batch/task/seed | Fixed and adaptive run paths, grades, cost metrics, actual adaptive changes, pairing status |
| `summary.json` | Selected batch | Planned/observed runs when a manifest exists; unobserved and completed pair coverage; graded-pair denominator; paired accuracy difference in percentage points; paired means and Jev token coverage |
| `issues.csv` | One data-quality issue | Unreadable result, duplicate completed run, missing side, or mismatched conditions |

**Pairing.** Only completed fixed/adaptive runs with the same explicit batch ID, task ID, seed, task text/reference, and configuration (other than mode, seed list, output path, and API key) form a pair. More than one completed run for a side makes that pair ambiguous; the script does not pick one. Historical runs without an ID remain in the run inventory but cannot be paired. The summary's accuracy denominator is `paired_graded`, not all tasks or all saved runs.

**Answer grade.** The built-in grader supports GSM8K numeric answers with an explicit `\boxed{number}`, `#### number`, or `Answer:`/`Final answer:` line and a numeric reference. If Qwen emits a `</think>` delimiter, only the final response after it is graded. It performs exact decimal comparison. Other tasks, conflicting explicit answers, or output without an explicit answer are `ungraded`; Jev Score is never treated as ground truth. Review the run-level `predicted_answer`, `reference_answer`, `grade_reason`, and original result path for each conclusion. This is deliberately conservative and can be extended with a separately validated grader for another dataset.

**Cost and changes.** `generated_tokens` comes from vLLM token IDs. Jev input/output tokens are summed from response `usage`; if any call lacks usage, run-level token totals are blank and the summary reports coverage. `jev_calls` is the runner's count; `observed_jev_requests` counts saved requests, which may differ after an interrupted call. `generation_seconds` and `jev_seconds` sum measured calls; `elapsed_seconds` includes setup and local processing, and can include cold model loading in the first run. An executed change requires a different value in the *next* round's `applied_parameters` and a matching next `generation_request`. A proposal in the last round is not counted. Compare timing within matched pairs and inspect outliers; these measurements are not hardware-independent speed benchmarks.

The index reads one result at a time and caches a compact row by path, size, modification time, and analyzer version in SQLite. Repeated reports avoid parsing unchanged large JSON files. The CSV files are plain data for plotting or statistical analysis; the script does not manufacture significance claims from small or incomplete batches.

The optional plot script requires Matplotlib (it can run in a separate plotting environment) and writes `performance.png`, `performance.svg`, and `performance.json`. Its answer-performance denominator is graded completed pairs; its cost panels use all completed pairs. The figure labels both denominators and Jev usage coverage. It compares adaptive control with fixed parameters under Jev scoring, not Jev against a no-Jev baseline.

To measure adaptive Jev control against generation without Jev, run a separate baseline batch with the same task set, seed, model, initial sampling values, and budgets. The baseline bypasses all Jev requests. Then analyze each batch and join them by task/seed and condition hash:

```powershell
python run.py run --mode baseline --experiment-id pilot-001-baseline
python scripts/analyze_results.py --outputs outputs --report-dir outputs/analysis/pilot-001-baseline --experiment-id pilot-001-baseline
python scripts/compare_to_baseline.py --baseline-report outputs/analysis/pilot-001-baseline --adaptive-report outputs/analysis/pilot-001 --baseline-id pilot-001-baseline --adaptive-id pilot-001 --output-dir outputs/analysis/pilot-001-vs-baseline
python scripts/plot_performance.py --control baseline --report-dir outputs/analysis/pilot-001-vs-baseline --output-prefix outputs/analysis/pilot-001-vs-baseline/performance
```

The join rejects absent, duplicate, incomplete, or mismatched runs and requires both manifests to cover the same planned task/seed set. A no-Jev baseline has zero Jev tokens and calls. This comparison still needs a larger, independently graded task set before it supports a general performance claim.

To open the local dashboard with an experiment-batch selector, run:

```powershell
python run.py dashboard
```

The command incrementally indexes saved `result.json` files, starts a local server, and opens the earliest-created experiment by default. Use the experiment-batch dropdown beside the other filters to switch batches in the same browser tab. A `compare` batch shows paired fixed/adaptive results; a single-mode `run` batch shows its own answer grades and costs. An available no-Jev baseline join adds Baseline to the paired page. Batches are not merged or compared automatically. Overview data stays compact and per-task traces load only when selected, including for large batches. Press `Ctrl+C` to stop the server. `--no-browser` prints the URL without opening a tab. To generate only one existing paired comparison, use `--baseline-compare-dir` and `--fixed-compare-dir` together.

Dashboard runtime files have their own folder: `outputs/dashboard/index/` holds the reusable analysis index, `outputs/dashboard/reports/<batch-hash>/` holds per-batch CSV exports, `outputs/dashboard/batches/<batch-hash>/` holds generated pages, and `outputs/dashboard/exports/` holds pages generated for a specified comparison. Manually requested analysis reports remain in `outputs/analysis/`; raw runs remain in `outputs/<timestamp>_<mode>/result.json` and manifests in `outputs/experiments/`. The dashboard files are ignored by Git and can be rebuilt from the raw results. Single-run detail indexes refer to local `result.json` paths, so another checkout must generate its own dashboard from its own results. Commit the launcher and source assets in `src/jev_vllm/` and `scripts/`, not the generated `outputs/` tree.

You can also generate the portable static files directly:

```powershell
python scripts/build_dashboard.py --baseline-compare-dir outputs/analysis/pilot-001-vs-baseline --fixed-compare-dir outputs/analysis/pilot-001 --output-dir outputs/dashboard/exports/pilot-001-dashboard
```

The Chinese/English dashboard has accuracy and cost cards, scalar traces, paired scatterplots, a joint token/time change matrix with arithmetic means, answer-outcome counts, Jev-call relationships, and a searchable, paginated task table. Blue identifies the selected control and red identifies adaptive in run comparisons. Selecting a point or task ID loads only that task's compact trace: normalized Jev Scores, actual per-round sampling values, timing, decisions, and verified next-round changes. The dashboard never embeds full prompts or responses for every task in its overview; task traces live in separate files. For over 100 tasks, overview curves show means of consecutive task bins; scatterplots sample at most 1,000 points. Aggregate cards, the joint-change matrix, outcome counts, and the table still use all filtered tasks. These charts are descriptive, not confidence intervals or significance tests.
