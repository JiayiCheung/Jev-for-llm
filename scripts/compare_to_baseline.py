"""Join a no-Jev baseline batch to a Jev-adaptive batch by task and seed."""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

FIELDS = (
    "grade_status",
    "generated_tokens",
    "jev_calls",
    "jev_input_tokens",
    "jev_output_tokens",
    "generation_seconds",
    "jev_seconds",
    "elapsed_seconds",
    "executed_changes",
    "path",
)


def load_rows(report_dir, experiment_id, mode):
    with (Path(report_dir) / "runs.csv").open(
        encoding="utf-8-sig", newline=""
    ) as stream:
        rows = [
            r
            for r in csv.DictReader(stream)
            if r["experiment_id"] == experiment_id and r["mode"] == mode
        ]
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["task_id"], row["seed"])].append(row)
    return grouped


def numeric(value):
    return float(value) if value not in (None, "") else None


def build(baseline_report, adaptive_report, baseline_id, adaptive_id, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    baselines = load_rows(baseline_report, baseline_id, "baseline")
    adaptives = load_rows(adaptive_report, adaptive_id, "adaptive")
    baseline_plan = json.loads(
        (Path(baseline_report) / "summary.json").read_text(encoding="utf-8")
    )
    adaptive_plan = json.loads(
        (Path(adaptive_report) / "summary.json").read_text(encoding="utf-8")
    )
    pairs = []
    for key in sorted(set(baselines) | set(adaptives)):
        left, right = baselines[key], adaptives[key]
        if len(left) != 1 or len(right) != 1:
            raise ValueError(
                f"Missing or duplicate run for {key}: baseline={len(left)} adaptive={len(right)}"
            )
        left, right = left[0], right[0]
        if left["status"] != "completed" or right["status"] != "completed":
            raise ValueError(f"Incomplete run for {key}")
        if (
            left["condition_hash"] != right["condition_hash"]
            or left["task_hash"] != right["task_hash"]
        ):
            raise ValueError(f"Condition or task mismatch for {key}")
        if (
            numeric(left["jev_calls"]) != 0
            or numeric(left["observed_jev_requests"]) != 0
        ):
            raise ValueError(f"Baseline made Jev calls for {key}")
        item = {
            "task_id": key[0],
            "seed": key[1],
            "condition_hash": left["condition_hash"],
        }
        for mode, source in (("baseline", left), ("adaptive", right)):
            for field in FIELDS:
                item[f"{mode}_{field}"] = source[field]
        pairs.append(item)
    if not pairs:
        raise ValueError("No matched baseline/adaptive runs")
    if len(pairs) != baseline_plan.get("planned_runs") or len(
        pairs
    ) != adaptive_plan.get("planned_pairs"):
        raise ValueError(
            "The two batch manifests do not cover the same complete task/seed set"
        )
    with (output_dir / "pairs.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(pairs[0]))
        writer.writeheader()
        writer.writerows(pairs)
    graded = [
        p
        for p in pairs
        if all(
            p[f"{mode}_grade_status"] in ("correct", "incorrect")
            for mode in ("baseline", "adaptive")
        )
    ]
    summary = {
        "baseline_id": baseline_id,
        "adaptive_id": adaptive_id,
        "paired_completed": len(pairs),
        "paired_graded": len(graded),
        "baseline_correct": sum(
            p["baseline_grade_status"] == "correct" for p in graded
        ),
        "adaptive_correct": sum(
            p["adaptive_grade_status"] == "correct" for p in graded
        ),
        "baseline_jev_calls": sum(numeric(p["baseline_jev_calls"]) for p in pairs),
        "adaptive_jev_calls": sum(numeric(p["adaptive_jev_calls"]) for p in pairs),
        "jev_usage_complete_pairs": sum(
            all(
                p[f"adaptive_jev_{direction}_tokens"] != ""
                for direction in ("input", "output")
            )
            for p in pairs
        ),
    }
    summary["accuracy_delta_pp"] = (
        round(
            100
            * (summary["adaptive_correct"] - summary["baseline_correct"])
            / len(graded),
            4,
        )
        if graded
        else None
    )
    for field in (
        "generated_tokens",
        "generation_seconds",
        "jev_seconds",
        "jev_input_tokens",
        "jev_output_tokens",
        "elapsed_seconds",
    ):
        summary[field + "_mean"] = {
            mode: round(
                sum(numeric(p[f"{mode}_{field}"]) for p in pairs) / len(pairs), 4
            )
            for mode in ("baseline", "adaptive")
        }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-report", required=True)
    parser.add_argument("--adaptive-report", required=True)
    parser.add_argument("--baseline-id", required=True)
    parser.add_argument("--adaptive-id", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            build(
                args.baseline_report,
                args.adaptive_report,
                args.baseline_id,
                args.adaptive_id,
                args.output_dir,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
