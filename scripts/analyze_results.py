"""Incrementally index Jev runs and export auditable paired comparisons."""

import argparse
import ast
import csv
import hashlib
import json
import re
import sqlite3
from collections import Counter as collections_counter
from collections import defaultdict
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path

VERSION = 6
NUMBER = r"[-+]?(?:\d+(?:,\d{3})*(?:\.\d+)?|\.\d+)"


def digest(value):
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def condition_hash(config):
    copy = deepcopy(config)
    copy.get("jev", {}).pop("api_key", None)
    copy.get("experiment", {}).pop("mode", None)
    # Seeds and output paths identify runs, not the scientific conditions.
    copy.get("experiment", {}).pop("seeds", None)
    copy.get("experiment", {}).pop("max_consecutive_errors", None)
    copy.get("paths", {}).pop("outputs", None)
    return digest(copy)


def _number(value):
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None


def _boxed_contents(text):
    r"""Contents of every \boxed{...} in order, with nested braces matched."""
    out = []
    for match in re.finditer(r"\\boxed\s*\{", text):
        depth, i = 1, match.end()
        while i < len(text) and depth:
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        if depth == 0:
            out.append((match.start(), text[match.end() : i - 1]))
    return out


WORDS = {
    word: value
    for value, word in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen "
        "fourteen fifteen sixteen seventeen eighteen nineteen twenty".split()
    )
}


def _exact(value):
    """Decimal and Fraction values compare exactly as fractions."""
    return Fraction(value) if isinstance(value, Decimal) else value  # None stays None


def _show(value):
    if isinstance(value, Decimal) or value.denominator == 1:
        return str(value) if isinstance(value, Decimal) else str(value.numerator)
    return format(Decimal(value.numerator) / Decimal(value.denominator), "f")


def _safe_value(text):
    r"""Value of a plain arithmetic expression such as `12 \times (3 + 4)`, or None.

    Only numbers, + - * / ^, parentheses and \frac are accepted; exponents must be small integers.
    """
    s = re.sub(r"\\(?:left|right)\b", "", text)
    s = re.sub(r"\\[,;!:]|\\ |\\\$|\$", "", s)
    s = re.sub(r"\\(?:times|cdot)\b|[×·]", "*", s)
    s = re.sub(r"\\div\b|÷", "/", s).replace("−", "-")
    s = re.sub(r"\^\s*\{([^{}]*)\}", r"**(\1)", s).replace("^", "**")
    if re.search(
        r"[\d.)]\s+[\d.(]", s
    ):  # two numbers side by side are not one expression
        return None
    s = s.replace(" ", "")
    for _ in range(20):
        s, count = re.subn(
            r"\\[dt]?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}", r"((\1)/(\2))", s
        )
        if not count:
            break
    s = s.replace("{", "(").replace("}", ")")
    s = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", s)
    if not s or not re.fullmatch(r"[0-9.+\-*/()]+", s):
        return None

    def walk(node):
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return Fraction(str(node.value))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = walk(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp):
            left, right = walk(node.left), walk(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if (
                isinstance(node.op, ast.Pow)
                and right.denominator == 1
                and abs(right) <= 200
            ):
                return left ** int(right)
        raise ValueError("unsupported")

    try:
        return walk(ast.parse(s, mode="eval"))
    except (SyntaxError, ValueError, ZeroDivisionError, OverflowError, RecursionError):
        return None


def _plain_number(text, units=False):
    r"""The number a short answer expression states, or None.

    Markup that only decorates a number is removed: $, \$, \!, \, , **, \mathbf{..},
    \text{..} units and a percent sign. Text after "=" wins, as in "100 - 84 = 16".
    With units=True words after the number are allowed (\boxed{16 hours}).
    Exact fractions, plain arithmetic and spelled-out numbers up to twenty are read as numbers.
    """
    fraction = re.fullmatch(
        r"\s*\$*\s*\\[dt]?frac\s*\{\s*("
        + NUMBER
        + r")\s*\}\s*\{\s*("
        + NUMBER
        + r")\s*\}\s*\$*\s*",
        text,
    )
    if fraction:
        top, bottom = _number(fraction.group(1)), _number(fraction.group(2))
        return top / bottom if top is not None and bottom else None
    # a unit in \text{..} is dropped, a number in \text{..} is kept
    text = re.sub(
        r"\\(?:text|mathrm|textrm)\s*\{([^{}]*)\}",
        lambda m: (
            m.group(1) if re.fullmatch(r"\s*" + NUMBER + r"\s*", m.group(1)) else " "
        ),
        text,
    )
    text = text.split("=")[-1]
    expression = text
    text = re.sub(
        r"\\(?:mathbf|textbf|boldsymbol|bf|mathit|displaystyle)\b\s*", "", text
    )
    text = re.sub(r"\\[,;!: ]|\\\$|\\%|[$*{}]|%", "", text)
    text = text.strip().rstrip(".").strip()
    if text.lower() in WORDS:  # \boxed{\textbf{three}}
        return Decimal(WORDS[text.lower()])
    pattern = r"(" + NUMBER + r")" + (r"(?:\s*[A-Za-z][A-Za-z ]*)?" if units else r"")
    found = re.fullmatch(pattern, text)
    if found:
        return _number(found.group(1))
    return _safe_value(expression) if re.search(r"[0-9]", expression) else None


def grade_answer(task, generated):
    if str(task.get("source", {}).get("dataset", "")).lower() != "gsm8k":
        return {
            "grade_status": "ungraded",
            "grade_reason": "unsupported_dataset",
            "predicted_answer": None,
            "reference_answer": None,
        }
    reference = str(task.get("reference_answer") or task.get("reference") or "")
    ref = re.search(r"####\s*(" + NUMBER + r")", reference) or re.search(
        r"^\s*(" + NUMBER + r")\s*$", reference
    )
    if not ref:
        return {
            "grade_status": "ungraded",
            "grade_reason": "missing_numeric_reference",
            "predicted_answer": None,
            "reference_answer": None,
        }
    truth = _number(ref.group(1))
    visible = (generated or "").rsplit("</think>", 1)[-1]

    def result(status, reason, predicted=None):
        return {
            "grade_status": status,
            "grade_reason": reason,
            "predicted_answer": predicted,
            "reference_answer": str(truth),
        }

    # Explicit final-answer markers, at most one value per kind. Only the LAST \boxed counts:
    # earlier boxes are intermediate results. "####" counts only as a line that holds just a
    # number (a Markdown heading such as "#### 1. Step" is not an answer). An "Answer:" line
    # counts when it holds just a number or a box; prose after it is a fallback only.
    markers = {}
    boxed = _boxed_contents(visible)
    if boxed:
        content = boxed[-1][1]
        value = _plain_number(content, units=True)
        if value is None:
            # An explicit final answer that is not a number cannot equal a numeric reference:
            # it is wrong, and the reason says which kind (words, or digits that form no number).
            kind = (
                "unreadable_final_answer"
                if re.search(r"[0-9]", content)
                else "non_numeric_final_answer"
            )
            return result("incorrect", kind, " ".join(content.split())[:60])
        markers["boxed"] = value
    hashes = re.findall(r"(?m)^[ \t]*####[ \t]*(" + NUMBER + r")[ \t]*$", visible)
    if hashes:
        markers["hashes"] = _number(hashes[-1])
    prose = []
    for label in re.finditer(
        r"(?i)(?:final\s+)?answer\s*\*{0,2}\s*[:：]([^\r\n]*)", visible
    ):
        line = label.group(1)
        inner = _boxed_contents(line)
        value = (
            _plain_number(inner[-1][1], units=True) if inner else _plain_number(line)
        )
        if value is not None:
            markers["label"] = value
        else:
            numbers = re.findall(NUMBER, line)
            if numbers:
                prose.append(numbers[-1])
    if not markers and prose:
        markers["prose"] = _number(prose[-1])
    if not markers:
        return result("ungraded", "no_explicit_final_answer")
    if len({_exact(value) for value in markers.values()}) != 1:
        return result("ungraded", "conflicting_explicit_answers")
    prediction = next(iter(markers.values()))
    if prediction is None or truth is None:
        return result("ungraded", "invalid_number")
    return result(
        "correct" if _exact(prediction) == _exact(truth) else "incorrect",
        "gsm8k_numeric_exact",
        _show(prediction),
    )


# context_budget is the only limit now; the other reasons occur in records made before
# the token, round and call caps were removed.
TRUNCATED_STOPS = {
    "context_budget",
    "token_budget",
    "round_budget",
    "token_or_context_budget",
    "jev_call_budget",
}


def classify_ending(stop_reason, grade_status):
    """answered: an explicit final answer exists. The other three are not savings."""
    if grade_status in ("correct", "incorrect"):
        return "answered"
    if stop_reason == "model_stop":
        return "stopped_no_answer"
    if stop_reason in TRUNCATED_STOPS:
        return "truncated"
    return "no_answer_other"


def summarize_run(record, path):
    config = record.get("config") or {}
    task = record.get("task") or {}
    experiment = record.get("experiment") or {}
    rounds = record.get("rounds") or []
    usage_in = usage_out = 0
    usage_missing = 0
    call_count = 0
    jev_seconds = generation_seconds = 0.0
    executed_changes = 0
    for index, row in enumerate(rounds):
        generation_seconds += float(row.get("generation_seconds") or 0)
        for stem in ("evaluation", "direction", "value", "checkpoint", "difference"):
            if row.get(stem + "_request") is None:
                continue
            call_count += 1
            jev_seconds += float(row.get(stem + "_seconds") or 0)
            usage = (row.get(stem + "_response") or {}).get("usage") or {}
            if isinstance(usage.get("input_tokens"), int) and isinstance(
                usage.get("output_tokens"), int
            ):
                usage_in += usage["input_tokens"]
                usage_out += usage["output_tokens"]
            else:
                usage_missing += 1
        if index + 1 < len(rounds) and row.get("epoch", 0) == rounds[index + 1].get(
            "epoch", 0
        ):
            next_row = rounds[index + 1]
            before = row.get("applied_parameters") or {}
            after = next_row.get("applied_parameters") or {}
            changed = [
                p
                for p in config.get("parameters", [])
                if before.get(p.get("name")) != after.get(p.get("name"))
            ]
            request = next_row.get("generation_request") or {}
            if changed and all(
                request.get(p.get("api_name", p.get("name")))
                == after.get(p.get("name"))
                for p in changed
            ):
                executed_changes += 1
    grade = grade_answer(task, record.get("generated", ""))
    return {
        "path": str(path),
        "experiment_id": experiment.get("id"),
        "run_id": experiment.get("run_id"),
        "task_id": task.get("id"),
        "task_hash": digest(
            {
                "prompt": task.get("prompt"),
                "reference": task.get("reference_answer", task.get("reference")),
            }
        ),
        "seed": record.get("seed"),
        "mode": config.get("experiment", {}).get("mode"),
        "condition_hash": condition_hash(config),
        "status": record.get("status"),
        "stop_reason": record.get("stop_reason"),
        "rounds": len(rounds),
        "generated_tokens": record.get(
            "total_generated_tokens", record.get("generated_token_count")
        ),
        "final_tokens": record.get("generated_token_count"),
        "wasted_tokens": record.get("wasted_tokens", 0),
        "restarts": len(record.get("restarts") or []),
        "prompt_tokens": record.get("prompt_token_count"),
        "jev_calls": record.get("jev_calls"),
        "observed_jev_requests": call_count,
        "jev_input_tokens": usage_in if usage_missing == 0 else None,
        "jev_output_tokens": usage_out if usage_missing == 0 else None,
        "jev_usage_missing_calls": usage_missing,
        "generation_seconds": round(generation_seconds, 6),
        "jev_seconds": round(jev_seconds, 6),
        "elapsed_seconds": record.get("elapsed_seconds"),
        "executed_changes": executed_changes,
        **grade,
        "ending": classify_ending(record.get("stop_reason"), grade["grade_status"]),
        "tokens_to_correct": (
            record.get("total_generated_tokens", record.get("generated_token_count"))
            if grade["grade_status"] == "correct"
            else None
        ),
    }


def _write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def analyze(outputs, report_dir, experiment_id=None):
    outputs, report_dir = Path(outputs), Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(report_dir / "index.sqlite")
    db.execute(
        "CREATE TABLE IF NOT EXISTS records (path TEXT PRIMARY KEY, size "
        "INTEGER, mtime_ns INTEGER, version INTEGER, row_json TEXT)"
    )
    runs, issues = [], []
    reused = 0
    try:
        for path in sorted(outputs.rglob("result.json")):
            stat = path.stat()
            key = str(path.resolve())
            cached = db.execute(
                "SELECT row_json FROM records WHERE path=? AND size=? AND mtime_ns=? AND version=?",
                (key, stat.st_size, stat.st_mtime_ns, VERSION),
            ).fetchone()
            if cached:
                row = json.loads(cached[0])
                reused += 1
            else:
                try:
                    row = summarize_run(
                        json.loads(path.read_text(encoding="utf-8")), key
                    )
                except (OSError, ValueError, TypeError, KeyError) as exc:
                    issues.append(
                        {"type": "unreadable_result", "key": key, "detail": str(exc)}
                    )
                    continue
                db.execute(
                    "INSERT OR REPLACE INTO records VALUES (?,?,?,?,?)",
                    (
                        key,
                        stat.st_size,
                        stat.st_mtime_ns,
                        VERSION,
                        json.dumps(row, ensure_ascii=False),
                    ),
                )
            runs.append(row)
        db.commit()
    finally:
        db.close()

    selected = [
        r for r in runs if experiment_id is None or r["experiment_id"] == experiment_id
    ]
    status_counts = defaultdict(int)
    grade_counts = defaultdict(int)
    for row in selected:
        status_counts[str(row["status"])] += 1
        grade_counts[row["grade_status"]] += 1
    groups = defaultdict(lambda: defaultdict(list))
    for row in selected:
        if (
            row["experiment_id"]
            and row["mode"] in ("fixed", "adaptive")
            and row["task_id"] is not None
            and row["seed"] is not None
        ):
            groups[(row["experiment_id"], row["task_id"], row["seed"])][
                row["mode"]
            ].append(row)
    pairs = []
    summary = {
        "indexed_runs": len(runs),
        "selected_runs": len(selected),
        "unbatched_runs": sum(not r["experiment_id"] for r in runs),
        "reused_records": reused,
        "run_status_counts": dict(status_counts),
        "run_grade_counts": dict(grade_counts),
        "paired_completed": 0,
        "paired_graded": 0,
        "fixed_correct": 0,
        "adaptive_correct": 0,
        "paired_executed_changes": 0,
        "ambiguous_pairs": 0,
        "missing_pairs": 0,
        "condition_mismatches": 0,
        "accuracy_delta_pp": None,
        "jev_usage_complete_pairs": 0,
    }
    for key, sides in sorted(groups.items()):
        completed = {
            mode: [r for r in sides[mode] if r["status"] == "completed"]
            for mode in ("fixed", "adaptive")
        }
        pair = {
            "experiment_id": key[0],
            "task_id": key[1],
            "seed": key[2],
            "status": None,
            "fixed_path": None,
            "adaptive_path": None,
            "fixed_grade": None,
            "adaptive_grade": None,
            "fixed_jev_calls": None,
            "adaptive_jev_calls": None,
            "fixed_elapsed_seconds": None,
            "adaptive_elapsed_seconds": None,
            "fixed_generated_tokens": None,
            "adaptive_generated_tokens": None,
            "fixed_jev_input_tokens": None,
            "adaptive_jev_input_tokens": None,
            "fixed_jev_output_tokens": None,
            "adaptive_jev_output_tokens": None,
            "fixed_generation_seconds": None,
            "adaptive_generation_seconds": None,
            "fixed_jev_seconds": None,
            "adaptive_jev_seconds": None,
            "adaptive_executed_changes": None,
        }
        if any(len(completed[mode]) > 1 for mode in completed):
            pair["status"] = "ambiguous_duplicate"
            summary["ambiguous_pairs"] += 1
        elif any(len(completed[mode]) == 0 for mode in completed):
            pair["status"] = "missing_completed_side"
            summary["missing_pairs"] += 1
        else:
            fixed, adaptive = completed["fixed"][0], completed["adaptive"][0]
            pair.update(
                fixed_path=fixed["path"],
                adaptive_path=adaptive["path"],
                fixed_grade=fixed["grade_status"],
                adaptive_grade=adaptive["grade_status"],
                adaptive_executed_changes=adaptive["executed_changes"],
            )
            for mode, source in (("fixed", fixed), ("adaptive", adaptive)):
                for field in (
                    "jev_calls",
                    "elapsed_seconds",
                    "generated_tokens",
                    "jev_input_tokens",
                    "jev_output_tokens",
                    "generation_seconds",
                    "jev_seconds",
                ):
                    pair[f"{mode}_{field}"] = source[field]
            if (
                fixed["condition_hash"] != adaptive["condition_hash"]
                or fixed["task_hash"] != adaptive["task_hash"]
            ):
                pair["status"] = "condition_mismatch"
                summary["condition_mismatches"] += 1
            else:
                pair["status"] = "paired"
                summary["paired_completed"] += 1
                summary["paired_executed_changes"] += adaptive["executed_changes"]
                if (
                    fixed["jev_usage_missing_calls"]
                    == adaptive["jev_usage_missing_calls"]
                    == 0
                ):
                    summary["jev_usage_complete_pairs"] += 1
                if fixed["grade_status"] in ("correct", "incorrect") and adaptive[
                    "grade_status"
                ] in ("correct", "incorrect"):
                    summary["paired_graded"] += 1
                    summary["fixed_correct"] += fixed["grade_status"] == "correct"
                    summary["adaptive_correct"] += adaptive["grade_status"] == "correct"
        if pair["status"] != "paired":
            issues.append(
                {
                    "type": pair["status"],
                    "key": "/".join(map(str, key)),
                    "detail": "Inspect runs.csv for all candidates",
                }
            )
        pairs.append(pair)
    n = summary["paired_graded"]
    if n:
        summary["accuracy_delta_pp"] = round(
            100 * (summary["adaptive_correct"] - summary["fixed_correct"]) / n, 1
        )
        summary["accuracy_resolution_pp"] = round(100 / n, 2)
        summary["accuracy_counts"] = {
            "fixed": summary["fixed_correct"],
            "adaptive": summary["adaptive_correct"],
        }
        both = [
            (p["fixed_grade"], p["adaptive_grade"])
            for p in pairs
            if p["status"] == "paired"
            and p["fixed_grade"] in ("correct", "incorrect")
            and p["adaptive_grade"] in ("correct", "incorrect")
        ]
        summary["discordant_pairs"] = {
            "adaptive_only": sum(f == "incorrect" and a == "correct" for f, a in both),
            "fixed_only": sum(f == "correct" and a == "incorrect" for f, a in both),
        }
    paired = [p for p in pairs if p["status"] == "paired"]
    ending = {r["path"]: r["ending"] for r in selected}
    summary["endings"] = {
        mode: dict(
            sorted(
                collections_counter(ending[p[f"{mode}_path"]] for p in paired).items()
            )
        )
        for mode in ("fixed", "adaptive")
    }
    answered = [
        p
        for p in paired
        if ending[p["fixed_path"]] == "answered"
        and ending[p["adaptive_path"]] == "answered"
    ]
    summary["answered_pairs"] = len(answered)
    summary["answered_cost_means"] = (
        {
            field: {
                mode: round(
                    sum(p[f"{mode}_{field}"] for p in answered) / len(answered), 4
                )
                for mode in ("fixed", "adaptive")
            }
            for field in ("generated_tokens", "generation_seconds", "jev_input_tokens")
            if answered
            and all(
                isinstance(p[f"{mode}_{field}"], (int, float))
                for p in answered
                for mode in ("fixed", "adaptive")
            )
        }
        if answered
        else None
    )
    for field in (
        "jev_calls",
        "elapsed_seconds",
        "generated_tokens",
        "generation_seconds",
        "jev_seconds",
    ):
        summary[field + "_mean"] = (
            {
                mode: round(
                    sum(
                        p[f"{mode}_{field}"]
                        for p in paired
                        if isinstance(p[f"{mode}_{field}"], (int, float))
                    )
                    / len(paired),
                    4,
                )
                for mode in ("fixed", "adaptive")
            }
            if paired
            and all(
                isinstance(p[f"{mode}_{field}"], (int, float))
                for p in paired
                for mode in ("fixed", "adaptive")
            )
            else None
        )
    usage_pairs = [
        p
        for p in paired
        if all(
            isinstance(p[f"{mode}_{field}"], int)
            for mode in ("fixed", "adaptive")
            for field in ("jev_input_tokens", "jev_output_tokens")
        )
    ]
    summary["jev_token_means"] = (
        {
            mode: {
                field: round(
                    sum(p[f"{mode}_{field}"] for p in usage_pairs) / len(usage_pairs), 4
                )
                for field in ("jev_input_tokens", "jev_output_tokens")
            }
            for mode in ("fixed", "adaptive")
        }
        if usage_pairs
        else None
    )
    if experiment_id:
        manifest_path = outputs / "experiments" / f"{experiment_id}.json"
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            summary["planned_runs"] = manifest.get("planned_runs")
            summary["observed_runs"] = len(selected)
            summary["planned_pairs"] = (
                len(manifest.get("task_ids", [])) * len(manifest.get("seeds", []))
                if set(manifest.get("modes", [])) == {"fixed", "adaptive"}
                else None
            )
            if summary["planned_pairs"] is not None:
                summary["unobserved_pairs"] = max(
                    0, summary["planned_pairs"] - len(pairs)
                )
                summary["completed_pair_coverage"] = (
                    round(summary["paired_completed"] / summary["planned_pairs"], 6)
                    if summary["planned_pairs"]
                    else None
                )
    _write_csv(
        report_dir / "runs.csv",
        selected,
        list(summarize_run({"config": {}, "task": {}}, "").keys()),
    )
    _write_csv(
        report_dir / "pairs.csv",
        pairs,
        list(pair.keys()) if pairs else ["experiment_id", "task_id", "seed", "status"],
    )
    _write_csv(report_dir / "issues.csv", issues, ["type", "key", "detail"])
    (report_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outputs", default="outputs")
    parser.add_argument("--report-dir", default="outputs/analysis")
    parser.add_argument(
        "--experiment-id",
        help="Filter to one explicit run batch; legacy runs remain unpaired",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            analyze(args.outputs, args.report_dir, args.experiment_id),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
