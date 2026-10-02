"""Build a lazy-loaded dashboard for one single-mode run batch."""

import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path

from build_dashboard import ASSETS, number


def build(report_dir, output_dir):
    report_dir, output_dir = Path(report_dir), Path(output_dir)
    with (report_dir / "runs.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    batches = {row["experiment_id"] for row in rows if row.get("experiment_id")}
    modes = {row["mode"] for row in rows if row.get("mode")}
    if len(batches) != 1 or len(modes) != 1:
        raise ValueError("Single-run dashboard requires one experiment ID and one mode")
    batch_id, mode = next(iter(batches)), next(iter(modes))
    (output_dir / "data").mkdir(parents=True, exist_ok=True)
    overview = []
    detail_index = {}
    for row in rows:
        if row.get("status") != "completed":
            continue
        path = Path(row["path"])
        key = hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:24]
        metrics = {"grade": row.get("grade_status"),
                   **{name: row.get(name) for name in (
                       "generated_tokens", "generation_seconds", "jev_seconds", "elapsed_seconds",
                       "jev_calls", "jev_input_tokens", "jev_output_tokens", "executed_changes")}}
        detail_index[key] = {"path": str(path), "metrics": metrics}
        generation_seconds = number(metrics["generation_seconds"])
        jev_seconds = number(metrics["jev_seconds"])
        overview.append({"key": key, "task": row["task_id"], "seed": row["seed"],
                         "grade": metrics["grade"], "tokens": number(metrics["generated_tokens"]),
                         "seconds": generation_seconds + jev_seconds if generation_seconds is not None and jev_seconds is not None else None,
                         "calls": number(metrics["jev_calls"]), "inputTokens": number(metrics["jev_input_tokens"]),
                         "outputTokens": number(metrics["jev_output_tokens"]), "changes": number(metrics["executed_changes"])})
    (output_dir / "data" / "detail-index.json").write_text(
        json.dumps(detail_index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (output_dir / "data" / "overview.js").write_text(
        "window.JEV_OVERVIEW = " + json.dumps({"batch": batch_id, "mode": mode,
        "completed": len(overview), "total": len(rows), "runs": overview},
        ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    (output_dir / "data" / "batches.js").write_text("window.JEV_BATCHES = " + json.dumps([{"id": batch_id, "slug": hashlib.sha256(batch_id.encode()).hexdigest()[:20], "modes": [mode], "tasks": len({row["task"] for row in overview})}], ensure_ascii=False) + ";\n", encoding="utf-8")
    for source, target in (("run.html", "index.html"), ("run.js", "run.js"), ("dashboard.css", "dashboard.css"), ("batch-switch.js", "batch-switch.js")):
        shutil.copy2(ASSETS / source, output_dir / target)
    print(f"Dashboard: {output_dir / 'index.html'} ({len(overview)} completed runs)")
    return batch_id, mode, len(overview)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    build(args.report_dir, args.output_dir)


if __name__ == "__main__":
    main()
