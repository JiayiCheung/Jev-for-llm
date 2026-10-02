"""Plot an audited fixed/adaptive batch from analyze_results.py exports."""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


FIXED = "#526675"
ADAPTIVE = "#b55d42"
LIGHT = "#e8e9e6"


def number(row, key):
    value = row.get(key)
    return float(value) if value not in (None, "") else None


def mean(values):
    return sum(values) / len(values) if values else None


def plot(report_dir, output_prefix, control="fixed"):
    report_dir = Path(report_dir)
    output_prefix = Path(output_prefix)
    with (report_dir / "pairs.csv").open(encoding="utf-8-sig", newline="") as stream:
        pairs = [row for row in csv.DictReader(stream) if row.get("status", "paired") == "paired"]
    if control == "baseline":
        for pair in pairs:
            for key, value in list(pair.items()):
                if key.startswith("baseline_"):
                    pair["fixed_" + key[len("baseline_"):]] = value
            pair["fixed_grade"] = pair["baseline_grade_status"]
            pair["adaptive_grade"] = pair["adaptive_grade_status"]
    summary = json.loads((report_dir / "summary.json").read_text(encoding="utf-8"))
    if not pairs:
        raise ValueError("No verified completed pairs; no performance figure can be drawn")
    graded = [p for p in pairs if p["fixed_grade"] in ("correct", "incorrect") and p["adaptive_grade"] in ("correct", "incorrect")]
    transitions = Counter(
        "both correct" if p["fixed_grade"] == p["adaptive_grade"] == "correct" else
        "adaptive only" if p["adaptive_grade"] == "correct" else
        "fixed only" if p["fixed_grade"] == "correct" else "both incorrect"
        for p in graded
    )
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                         "axes.titleweight": "bold", "figure.facecolor": "white", "axes.facecolor": "white"})
    fig, axes = plt.subplots(2, 3, figsize=(15, 8.4))
    fig.subplots_adjust(left=0.075, right=0.98, bottom=0.12, top=0.85, wspace=0.38, hspace=0.42)
    control_label = "No Jev" if control == "baseline" else "Fixed"
    fig.suptitle(f"{control_label} vs adaptive · paired inference comparison", y=0.98, fontsize=18, fontweight="bold")
    context = "baseline makes zero Jev calls" if control == "baseline" else f"{summary.get('paired_executed_changes', 0)} applied adjustments · both arms use Jev Score"
    fig.text(0.5, 0.915, f"{len(pairs)} completed pairs · {len(graded)} independently graded · {context}",
             ha="center", color="#555555", fontsize=10)

    ax = axes[0, 0]
    if graded:
        correct = [sum(p[f"{mode}_grade"] == "correct" for p in graded) for mode in ("fixed", "adaptive")]
        bars = ax.bar([control_label, "Adaptive"], [100 * x / len(graded) for x in correct], color=[FIXED, ADAPTIVE], width=0.58)
        for bar, count in zip(bars, correct):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height()+2, f"{count}/{len(graded)}", ha="center")
        ax.set_ylim(0, 112)
        ax.set_ylabel("Exact-answer accuracy (%)")
    else:
        ax.text(0.5, 0.5, "No graded pairs", ha="center", va="center", transform=ax.transAxes)
    ax.set_title("A  Answer performance", loc="left")

    ax = axes[0, 1]
    labels = ["both correct", "adaptive only", f"{control} only", "both incorrect"]
    values = [transitions[label.replace(control, "fixed")] for label in labels]
    ax.barh(labels[::-1], values[::-1], color=["#a8a8a2", ADAPTIVE, FIXED, "#6c8069"][::-1])
    ax.set_xlim(0, max(values + [1]) * 1.2)
    ax.set_xlabel("Tasks")
    for y, value in enumerate(values[::-1]):
        ax.text(value + 0.05, y, str(value), va="center")
    ax.set_title("B  Paired outcome transitions", loc="left")

    ax = axes[0, 2]
    sorted_pairs = sorted(pairs, key=lambda p: p["task_id"])
    token_delta = [number(p, "adaptive_generated_tokens") - number(p, "fixed_generated_tokens") for p in sorted_pairs]
    ids = [p["task_id"].replace("gsm8k_train_", "") for p in sorted_pairs]
    ax.barh(ids[::-1], token_delta[::-1], color=[ADAPTIVE if x >= 0 else FIXED for x in token_delta[::-1]])
    ax.axvline(0, color="#333333", linewidth=0.8)
    ax.set_xlabel(f"Adaptive − {control} Qwen tokens")
    ax.set_title("C  Generation cost by task", loc="left")

    ax = axes[1, 0]
    latency_totals = []
    for i, mode in enumerate(("fixed", "adaptive")):
        gen = mean([number(p, f"{mode}_generation_seconds") for p in pairs])
        jev = mean([number(p, f"{mode}_jev_seconds") for p in pairs])
        latency_totals.append(gen + jev)
        ax.bar(i, gen, color=[FIXED, ADAPTIVE][i], label="Qwen generate" if i == 0 else None)
        ax.bar(i, jev, bottom=gen, color="#c9cbc6", label="Jev calls" if i == 0 else None)
        ax.text(i, gen + jev + 0.5, f"{gen + jev:.1f}s", ha="center")
    ax.set_xticks([0, 1], [control_label, "Adaptive"])
    ax.set_ylabel("Mean measured seconds / task")
    ax.set_ylim(0, max(latency_totals) * 1.28)
    ax.legend(frameon=False, fontsize=8, loc="upper center", ncol=2)
    ax.set_title("D  Generation + Jev latency", loc="left")

    ax = axes[1, 1]
    fixed_calls = [number(p, "fixed_jev_calls") for p in pairs]
    adaptive_calls = [number(p, "adaptive_jev_calls") for p in pairs]
    if control == "baseline":
        ax.bar([control_label, "Adaptive"], [mean(fixed_calls), mean(adaptive_calls)], color=[FIXED, ADAPTIVE], width=0.58)
        ax.set_ylabel("Mean Jev calls / task")
    else:
        lim = max(fixed_calls + adaptive_calls + [1]) + 1
        ax.plot([0, lim], [0, lim], linestyle="--", color="#999999", linewidth=1)
        ax.scatter(fixed_calls, adaptive_calls, color=ADAPTIVE, s=38)
        ax.set_xlim(0, lim)
        ax.set_ylim(0, lim)
        ax.set_xlabel("Fixed Jev calls / task")
        ax.set_ylabel("Adaptive Jev calls / task")
    ax.set_title("E  Evaluator request cost", loc="left")

    ax = axes[1, 2]
    complete_usage = [p for p in pairs if all(number(p, f"{mode}_jev_{direction}_tokens") is not None
                                           for mode in ("fixed", "adaptive") for direction in ("input", "output"))]
    if complete_usage:
        for i, mode in enumerate(("fixed", "adaptive")):
            incoming = mean([number(p, f"{mode}_jev_input_tokens") for p in complete_usage])
            outgoing = mean([number(p, f"{mode}_jev_output_tokens") for p in complete_usage])
            ax.bar(i, incoming, color=[FIXED, ADAPTIVE][i], label="Input" if i == 0 else None)
            ax.bar(i, outgoing, bottom=incoming, color="#c9cbc6", label="Output" if i == 0 else None)
        ax.set_xticks([0, 1], [control_label, "Adaptive"])
        ax.set_ylabel("Mean Jev tokens / task")
        ax.legend(frameon=False, fontsize=8)
    else:
        ax.text(0.5, 0.5, "No complete usage pairs", ha="center", va="center", transform=ax.transAxes)
    ax.set_title(f"F  Jev token usage · {len(complete_usage)}/{len(pairs)} covered", loc="left")

    foot = "Exploratory sample. Baseline makes no Jev calls." if control == "baseline" else "Exploratory sample. Fixed still calls Jev."
    fig.text(0.5, 0.035, foot + " Timing excludes setup; correctness requires explicit GSM8K answers.",
             ha="center", fontsize=9, color="#555555")
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_prefix.with_suffix(".png"), dpi=190, facecolor="white")
    fig.savefig(output_prefix.with_suffix(".svg"), facecolor="white")
    plt.close(fig)
    metrics = {
        "paired_completed": len(pairs), "paired_graded": len(graded),
        "transitions": {(f"{control} only" if control == "baseline" and label == "fixed only" else label): count
                        for label, count in transitions.items()},
        "accuracy_delta_pp": summary.get("accuracy_delta_pp"), "usage_complete_pairs": len(complete_usage),
        "net_additional_correct": sum(p["adaptive_grade"] == "correct" for p in graded) - sum(p["fixed_grade"] == "correct" for p in graded),
        "extra_jev_calls_total": sum(number(p, "adaptive_jev_calls") - number(p, "fixed_jev_calls") for p in pairs),
        "mean_generated_tokens": {label: mean([number(p, f"{mode}_generated_tokens") for p in pairs]) for label, mode in ((control, "fixed"), ("adaptive", "adaptive"))},
        "mean_jev_calls": {label: mean([number(p, f"{mode}_jev_calls") for p in pairs]) for label, mode in ((control, "fixed"), ("adaptive", "adaptive"))},
        "mean_generation_seconds": {label: mean([number(p, f"{mode}_generation_seconds") for p in pairs]) for label, mode in ((control, "fixed"), ("adaptive", "adaptive"))},
        "mean_jev_seconds": {label: mean([number(p, f"{mode}_jev_seconds") for p in pairs]) for label, mode in ((control, "fixed"), ("adaptive", "adaptive"))},
        "mean_jev_tokens_complete_pairs": {label: {direction: mean([number(p, f"{mode}_jev_{direction}_tokens") for p in complete_usage])
                                                   for direction in ("input", "output")} for label, mode in ((control, "fixed"), ("adaptive", "adaptive"))},
    }
    output_prefix.with_suffix(".json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", required=True)
    parser.add_argument("--output-prefix", required=True)
    parser.add_argument("--control", choices=["fixed", "baseline"], default="fixed")
    args = parser.parse_args()
    print(json.dumps(plot(args.report_dir, args.output_prefix, args.control), indent=2))


if __name__ == "__main__":
    main()
