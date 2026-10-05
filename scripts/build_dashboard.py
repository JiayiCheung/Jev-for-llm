"""Build a portable, lazy-loaded dashboard from strict paired reports."""

import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path(__file__).resolve().parent / "dashboard"


def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def number(value):
    if value in (None, ""):
        return None
    return float(value) if "." in str(value) else int(value)


def compact_rounds(record):
    source = record.get("rounds") or []
    names = [p["name"] for p in record.get("config", {}).get("parameters", [])]
    output = []
    for index, entry in enumerate(source):
        params = entry.get("applied_parameters") or {}
        upcoming = source[index + 1] if index + 1 < len(source) else None
        next_params = (upcoming or {}).get("applied_parameters") or {}
        next_request = (upcoming or {}).get("generation_request") or {}
        definitions = record.get("config", {}).get("parameters", [])
        changed = [p["name"] for p in definitions if params.get(p["name"]) != next_params.get(p["name"])] if upcoming else []
        executed = bool(changed and all(next_request.get(p.get("api_name", p["name"])) == next_params.get(p["name"]) for p in definitions if p["name"] in changed))
        usage_in = usage_out = 0
        for stem in ("evaluation", "direction", "value"):
            usage = ((entry.get(stem + "_response") or {}).get("usage") or {})
            usage_in += usage.get("input_tokens") or 0
            usage_out += usage.get("output_tokens") or 0
        scores = entry.get("scores") or {}
        output.append({
            "step": entry.get("step", index), "tokenStart": entry.get("token_start"), "tokenEnd": entry.get("token_end"),
            "epoch": entry.get("epoch") or 0, "abandoned": bool(entry.get("abandoned")),
            "tokens": (entry.get("token_end") or 0) - (entry.get("token_start") or 0),
            "scores": {name: value.get("normalized") for name, value in scores.items() if isinstance(value, dict)},
            "utility": (entry.get("decision") or {}).get("utility"),
            "trouble": (entry.get("decision") or {}).get("trouble"),
            "worst": (entry.get("decision") or {}).get("worst"),
            "parameters": {name: params.get(name) for name in names if name in params},
            "generationSeconds": entry.get("generation_seconds"),
            "jevSeconds": sum(entry.get(stem + "_seconds") or 0 for stem in ("evaluation", "direction", "value")),
            "jevCalls": sum(entry.get(stem + "_request") is not None for stem in ("evaluation", "direction", "value")),
            "jevInputTokens": usage_in, "jevOutputTokens": usage_out,
            "action": (entry.get("decision") or {}).get("action"),
            "reason": (entry.get("decision") or {}).get("reason"),
            "proposal": bool(entry.get("decision_will_execute")),
            "executedNextRound": executed,
            "changedNextRound": changed if executed else [],
        })
    return output


def parameter_activity(record):
    """Per parameter: [times Jev was asked, times it chose anything but keep], abandoned rounds excluded."""
    counts = {}
    for entry in record.get("rounds") or []:
        if entry.get("abandoned"):
            continue
        answers = (entry.get("direction_response") or {}).get("answers") or {}
        for key, answer in answers.items():
            if not key.startswith("direction_") or not isinstance(answer, dict):
                continue
            seen = counts.setdefault(key[len("direction_"):], [0, 0])
            seen[0] += 1
            seen[1] += answer.get("choice") != "keep"
    return counts


def compact_run(path, metrics, include_task=False):
    record = json.loads(Path(path).read_text(encoding="utf-8"))
    result = {
        "wastedTokens": record.get("wasted_tokens") or 0, "restarts": len(record.get("restarts") or []),
        "activity": parameter_activity(record),
        "grade": metrics["grade"], "generatedTokens": number(metrics["generated_tokens"]),
        "generationSeconds": number(metrics["generation_seconds"]),
        "jevSeconds": number(metrics["jev_seconds"]), "elapsedSeconds": number(metrics["elapsed_seconds"]),
        "jevCalls": number(metrics["jev_calls"]), "jevInputTokens": number(metrics["jev_input_tokens"]),
        "jevOutputTokens": number(metrics["jev_output_tokens"]), "executedChanges": number(metrics.get("executed_changes") or 0),
        "stopReason": record.get("stop_reason"), "rounds": compact_rounds(record),
        "finalAnswer": (record.get("generated") or "").rsplit("</think>", 1)[-1][-1200:],
        "resultPath": str(Path(path).resolve()),
    }
    if include_task:
        result["task"] = record.get("task") or {}
    return result


def metrics(row, prefix):
    return {name: row.get(prefix + key, "") for name, key in {
        "grade": "grade_status" if "baseline_grade_status" in row else "grade",
        "generated_tokens": "generated_tokens", "generation_seconds": "generation_seconds",
        "jev_seconds": "jev_seconds", "elapsed_seconds": "elapsed_seconds", "jev_calls": "jev_calls",
        "jev_input_tokens": "jev_input_tokens", "jev_output_tokens": "jev_output_tokens",
        "executed_changes": "executed_changes",
    }.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-compare-dir", type=Path)
    parser.add_argument("--fixed-compare-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    baseline = rows(args.baseline_compare_dir / "pairs.csv") if args.baseline_compare_dir else None
    fixed = rows(args.fixed_compare_dir / "pairs.csv")
    paired_fixed = [r for r in fixed if r["status"] == "paired"]
    fixed_by_key = {(r["task_id"], r["seed"]): r for r in paired_fixed}
    if len(fixed_by_key) != len(paired_fixed):
        raise ValueError("Fixed/adaptive report contains duplicate completed pairs")
    if not paired_fixed:
        raise ValueError("Fixed/adaptive report has no paired runs")
    output = args.output_dir.resolve()
    data_dir = output / "data" / "tasks"
    data_dir.mkdir(parents=True, exist_ok=True)
    summary = []
    activity = {}
    seen = set()
    for pair in baseline if baseline is not None else paired_fixed:
        key = (pair["task_id"], pair["seed"])
        if key in seen:
            raise ValueError(f"Duplicate baseline pair: {key}")
        seen.add(key)
        if key not in fixed_by_key:
            continue
        other = fixed_by_key[key]
        if Path(pair["adaptive_path"]).resolve() != Path(other["adaptive_path"]).resolve():
            raise ValueError(f"Adaptive run mismatch: {key}")
        identifier = hashlib.sha256((key[0] + "\0" + key[1]).encode()).hexdigest()[:24]
        modes = {"fixed": compact_run(other["fixed_path"], metrics(other, "fixed_")),
                 "adaptive": compact_run(pair["adaptive_path"], metrics(pair, "adaptive_"), include_task=True)}
        if baseline is not None:
            modes = {"baseline": compact_run(pair["baseline_path"], metrics(pair, "baseline_")), **modes}
        prompt = modes["adaptive"].pop("task")
        detail = {"id": pair["task_id"], "seed": number(pair["seed"]), "prompt": prompt.get("prompt", ""),
                  "reference": prompt.get("reference_answer") or prompt.get("reference", ""), "modes": modes}
        (data_dir / (identifier + ".js")).write_text("window.JEV_TASKS[" + json.dumps(identifier) + "] = " + json.dumps(detail, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
        summary.append({"key": identifier, "task": pair["task_id"], "seed": number(pair["seed"]),
                        "modes": {mode: {k: v for k, v in run.items() if k in ("grade", "generatedTokens", "generationSeconds", "jevSeconds", "elapsedSeconds", "jevCalls", "jevInputTokens", "jevOutputTokens", "executedChanges", "stopReason", "wastedTokens", "restarts")}
                                  for mode, run in modes.items()}})
        for name, (asked, changed) in modes["adaptive"]["activity"].items():
            total = activity.setdefault(name, [0, 0])
            total[0] += asked
            total[1] += changed
    if not summary:
        raise ValueError("No completed pairs are shared by the selected reports")
    available = ["baseline", "fixed", "adaptive"] if baseline is not None else ["fixed", "adaptive"]
    batch_id = fixed[0].get("experiment_id") or "experiment"
    (output / "data" / "overview.js").write_text("window.JEV_OVERVIEW = " + json.dumps({"tasks": summary, "count": len(summary), "modes": available, "batch": batch_id, "parameterActivity": activity}, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    (output / "data" / "batches.js").write_text("window.JEV_BATCHES = " + json.dumps([{"id": batch_id, "slug": hashlib.sha256(batch_id.encode()).hexdigest()[:20], "modes": available, "tasks": len(summary)}], ensure_ascii=False) + ";\n", encoding="utf-8")
    for asset in ("index.html", "explorer.css", "core.js", "explorer.js", "tab-overview.js", "tab-curves.js", "tab-judge.js", "tab-tasks.js", "batch-switch.js"):
        shutil.copy2(ASSETS / asset, output / asset)
    print(f"Dashboard: {output / 'index.html'} ({len(summary)} paired tasks, {len(summary)*len(available)} runs)")


if __name__ == "__main__":
    main()
