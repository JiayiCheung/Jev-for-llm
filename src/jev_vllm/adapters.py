import math


def number(value, low, high):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not low <= value <= high
    ):
        raise ValueError(f"Score field must be a finite number in [{low}, {high}]")

    return float(value)


def parse_scores(response, questions):
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


def build_evaluation(task, text, recent, step, jev_config):
    return {
        "model": jev_config["model"],
        "questions": jev_config["questions"],
        "state": {"task": task, "generated": text, "recent": recent, "step": step},
    }
