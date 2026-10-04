"""What the controller computes from Jev's rubric scores and shows back to Jev.

Everything here is arithmetic or bookkeeping on Jev's own answers. Nothing maps a symptom
to a parameter or a direction: that connection is left to Jev.
"""

from .jev_requests import RECENT, describe_value


def symptom_names(questions):
    """Rubrics whose score describes a problem: 0 = absent, 4 = severe."""
    return [name for name, q in questions.items() if q["kind"] == "symptom"]


def gauges(scores, questions):
    """Per symptom: `severity` (expected level / highest level) and `p_severe` (level 3 or 4)."""
    return {
        name: {
            "severity": round(scores[name]["normalized"], 3),
            "p_severe": round(scores[name]["p_severe"], 3),
        }
        for name in symptom_names(questions)
    }


def trouble(scores, questions, weights):
    """The largest weighted severity and the symptom that gives it.

    The largest is used instead of the mean because a symptom is a rare event: one severe
    symptom among four absent ones would barely move an average.
    """
    top = max(weights.values())
    scaled = {
        name: weights[name] / top * scores[name]["normalized"]
        for name in symptom_names(questions)
    }
    worst = max(scaled, key=scaled.get)

    return round(scaled[worst], 3), worst


def _scored(rows):
    return [row for row in rows if "scores" in row]


def _describe_change(spec, old, new):
    """`old→new` for plain values, the reviewed label for token groups and presets."""
    if isinstance(old, (dict, list)) or isinstance(new, (dict, list)):
        return describe_value(spec, old, new)

    return f"{old}→{new}"


def recent_changes(rows, specs):
    """Parameter changes made before each of the last segments, oldest first."""
    by_name = {spec["name"]: spec for spec in specs}
    entries = []

    for index in range(max(1, len(rows) - RECENT + 1), len(rows) + 1):
        row = rows[index - 1]
        before = rows[index - 2]["applied_parameters"] if index >= 2 else None
        changes = {}

        if before is not None:
            for name in by_name:
                old, new = before[name], row["applied_parameters"][name]

                if old != new:
                    changes[name] = _describe_change(by_name[name], old, new)

        entries.append({"segment": row["step"] + 1, "changes": changes or "none"})

    return entries


def parameter_ages(rows, specs, initial):
    """For each parameter that differs from its initial value: segments in effect."""
    current = rows[-1]["applied_parameters"]
    ages = {}

    for spec in specs:
        name = spec["name"]

        if current[name] == initial[name]:
            continue

        age = 0

        for row in reversed(rows):
            if row["applied_parameters"][name] != current[name]:
                break

            age += 1

        ages[name] = age

    return ages


def persistence(scored, questions, threshold):
    """Per symptom: consecutive latest segments in which p_severe reached `threshold`."""
    counts = {}

    for name in symptom_names(questions):
        count = 0

        for row in reversed(scored):
            if row["scores"][name]["p_severe"] < threshold:
                break

            count += 1

        counts[name] = count

    return counts


def build(rows, c, specs):
    """The signals for the segment just scored. `rows` are the kept rows, newest last.

    `specs` are the parameter definitions; rows without scores (the probe segments
    generated after a restart) are skipped where scores are needed.
    """
    questions = c["jev"]["questions"]
    weights = c["policy"]["symptom_weights"]
    scored = _scored(rows)
    now = scored[-1]["scores"]
    top, worst = trouble(now, questions, weights)
    first = scored[0]["scores"]
    first_top, first_worst = trouble(first, questions, weights)

    return {
        "gauges_now": gauges(now, questions),
        "trouble_now": top,
        "worst": worst,
        "at_start": {"trouble": first_top, "gauges": gauges(first, questions)},
        "recent_3": [
            {
                "segment": row["step"] + 1,
                "trouble": trouble(row["scores"], questions, weights)[0],
                "severity": {
                    name: round(row["scores"][name]["normalized"], 3)
                    for name in symptom_names(questions)
                },
            }
            for row in scored[-RECENT:]
        ],
        "persistence": persistence(
            scored, questions, c["policy"]["signals"]["persistence_threshold"]
        ),
        "my_recent_changes": recent_changes(rows, specs),
        "parameter_ages": parameter_ages(rows, specs, c["sampling"]),
    }


def trace(rows, questions, weights):
    """Per scored segment: `on_track` and `trouble`, for the restart check."""
    return [
        {
            "round": row["step"] + 1,
            "on_track": round(row["scores"]["on_track"]["normalized"], 3),
            "trouble": trouble(row["scores"], questions, weights)[0],
        }
        for row in _scored(rows)
    ]
