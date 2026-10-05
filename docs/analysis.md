# Result analysis

`scripts/analyze_results.py` builds an incremental local index of `result.json` files and exports `runs.csv`, `pairs.csv`, `issues.csv`, and `summary.json`. It uses only the Python standard library. The index and reports belong under `outputs/`, which is ignored by Git.

```powershell
python run.py compare --experiment-id pilot-001
python scripts/analyze_results.py --outputs outputs --report-dir outputs/analysis/pilot-001 --experiment-id pilot-001
python scripts/plot_performance.py --report-dir outputs/analysis/pilot-001 --output-prefix outputs/analysis/pilot-001/performance
```

For a new batch, omit `--experiment-id` and retain the ID printed by `run.py`; a manifest is saved in `outputs/experiments/<id>.json`. After an interruption, use the same ID with `--resume` and the same tasks/configuration. Completed task/seed/mode runs are skipped; interrupted, errored or cut-off records are ignored and those runs restart from their first segment (the old folders stay on disk but only `completed` runs are analysed). A changed plan is rejected. Resume prints how many runs are complete, how many unfinished attempts were ignored, and a progress line with a time estimate after every run. A `compare` batch contains only fixed and adaptive modes; both call Jev for Score. It is not a no-Jev baseline.

The exports have three levels:

| File | Unit | Key evidence |
|---|---|---|
| `runs.csv` | One saved run | Batch, task, seed, mode, status, stop reason, independent answer grade, generated tokens, Jev calls and token usage, timing, executed parameter changes, source path |
| `pairs.csv` | One batch/task/seed | Fixed and adaptive run paths, grades, cost metrics, actual adaptive changes, pairing status |
| `summary.json` | Selected batch | Planned/observed runs when a manifest exists; unobserved and completed pair coverage; graded-pair denominator; paired accuracy difference in percentage points; paired means and Jev token coverage |
| `issues.csv` | One data-quality issue | Unreadable result, duplicate completed run, missing side, or mismatched conditions |

**Pairing.** Only completed fixed/adaptive runs with the same explicit batch ID, task ID, seed, task text/reference, and configuration (other than mode, seed list, output path, and API key) form a pair. More than one completed run for a side makes that pair ambiguous; the script does not pick one. Historical runs without an ID remain in the run inventory but cannot be paired. The summary's accuracy denominator is `paired_graded`, not all tasks or all saved runs.

**Answer grade.** The built-in grader supports GSM8K numeric answers with an explicit `\boxed{number}`, `#### number`, or `Answer:`/`Final answer:` line and a numeric reference. If Qwen emits a `</think>` delimiter, only the final response after it is graded. Only the last `\boxed{}` counts, because earlier boxes are intermediate results; markup that merely decorates the number (`$`, `\$`, `\!`, `\mathbf{}`, `\text{}` units, `%`, a thousands separator, or `... = 16`) is removed, and exact fractions such as `\frac{10}{2}`, plain arithmetic such as `12 \times (3 + 4)` (numbers, `+ - × ÷ ^`, parentheses and `\frac` only, evaluated exactly) and spelled-out numbers up to twenty are read as numbers. A `####` line counts only when it holds just a number, so Markdown headings such as `#### 1. Step` are ignored, and an `Answer:` line counts as a marker only when it holds just a number or a box; a prose line after `Answer:` is used only when nothing else is explicit. The comparison is exact. A final box that holds no number (`None`, `Unknown`) or digits that form no number (`\$7,0`, `\mathtt{258.k}`) is an explicit answer that cannot match a numeric reference, so it is graded `incorrect` with `grade_reason` `non_numeric_final_answer` or `unreadable_final_answer`, never replaced by an earlier number. Other tasks, different values from different kinds of explicit marker (for example a box and a separate `Answer:` number), or output without an explicit answer are `ungraded`; Jev Score is never treated as ground truth. Review the run-level `predicted_answer`, `reference_answer`, `grade_reason`, and original result path for each conclusion. This is deliberately conservative and can be extended with a separately validated grader for another dataset.

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

The Chinese/English dashboard is laid out like TensorBoard: a tab bar, a settings column (batch, control, answer filter, task search by regex, which runs to draw, curve smoothing) and cards that each hold one chart or table with SVG and CSV download. **Overview** shows accuracy against mean generated tokens with 95% bootstrap intervals, paired token and request-time scatterplots, the paired 2×2 outcome table with the exact McNemar test, a per-task cost breakdown (generation, Jev requests and tokens, restarts, tokens wasted in restarts) and a stratification by control generation length. **Curves** plots every per-segment quantity (the six scores, trouble, cumulative tokens, timings, each sampling parameter) averaged over the selected tasks with a 95% band and TensorBoard-style smoothing, filtered by tag. **Distributions** shows the distribution of the per-task token change and median/quartile/decile bands per segment. **Judge** shows `on_track` calibration and AUC against the final answer grade, `on_track` by final outcome and how often each symptom is flagged. **Behavior** shows the direction of each parameter change, how often each parameter was asked about and changed, the segment of the first change, the change rate by trouble level and by worst symptom, and the tasks with restarts. **Tasks** shows every task as a line across its run-level metrics (parallel coordinates) and a sortable, paginated table. Selecting a task opens a drawer with its prompt, run summaries, a per-segment chart of any tag for the compared runs and the final answers. Gray identifies the selected control and blue identifies adaptive. Per-task records are loaded lazily; the Curves, Distributions, Judge, Behavior and Tasks tabs read the round records of every selected task once. These charts are descriptive; intervals are bootstrap intervals over tasks, not a substitute for a pre-specified analysis.

## Reading the results: suspect reference labels

Jev sees only the generated text, never the reference answer, so a reasoning that is internally consistent but disagrees with the reference scores well on `on_track`. A task can also have a reference that follows one of two reasonable readings of the question (for example "speed improved by 10%" counted as "time reduced by 10%"). Both modes are paired by task and seed, so such tasks add noise to both sides rather than favour one.

Rule, fixed before the results are read: a task is flagged as a suspect label when every run of it (baseline, fixed and adaptive, all seeds) ends with the same final number and that number differs from the reference. Report accuracy twice, once over all tasks and once without the flagged ones, and inspect each flagged task by hand instead of removing it automatically. If the two reports lead to the same conclusion, label ambiguity does not affect the claim. The 20 tasks used while the scoring design was debugged are excluded from the pilot sample (`data/tasks_pilot100.manifest.json`, `excluded_seen`).
