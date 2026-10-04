"""Validation and normalisation of Jev Score answers and the record copies."""

import math


def number(value, low, high):
    """Return `value` as a float; it must be a finite number in [low, high]."""
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not low <= value <= high
    ):
        raise ValueError(f"Score field must be a finite number in [{low}, {high}]")

    return float(value)


def parse_scores(response, questions):
    """Validate Jev's Score answers and add each score divided by its highest level."""
    result = {}

    for name in questions:
        answer = response["answers"][name]

        if answer.get("type") != "score":
            raise ValueError(f"{name} must return a Score response")

        maximum = len(questions[name]["criteria"]) - 1
        score = number(answer["score"], 0, maximum)
        probabilities = answer["probabilities"]

        if set(probabilities) != {str(i) for i in range(maximum + 1)}:
            raise ValueError(f"{name} has mismatched probability level keys")

        probs = [number(probabilities[str(i)], 0, 1) for i in range(maximum + 1)]

        if abs(sum(probs) - 1) > 0.02:
            raise ValueError(f"{name} probabilities do not sum to 1")

        result[name] = {
            "score": score,
            "normalized": score / maximum,
            "probabilities": probabilities,
        }

        if questions[name].get("kind") == "symptom":
            # Probability that the symptom is clearly present: the two highest levels.
            result[name]["p_severe"] = sum(probs[-2:])

    return result


def score_response(response):
    """Keep only supported Score answer fields in experiment records."""
    from copy import deepcopy

    result = deepcopy(response)
    if isinstance(result.get("answers"), dict):
        for name, answer in result["answers"].items():
            if isinstance(answer, dict):
                result["answers"][name] = {
                    key: value
                    for key, value in answer.items()
                    if key in ("type", "score", "probabilities", "legend")
                }
    return result


def choice_response(response):
    """Record Choice outputs without the redundant confidence field."""
    result = {
        "answers": {
            name: {
                key: answer[key]
                for key in ("type", "choice", "probabilities")
                if key in answer
            }
            for name, answer in response["answers"].items()
        }
    }
    for key in ("model", "usage"):
        if key in response:
            result[key] = response[key]
    return result
