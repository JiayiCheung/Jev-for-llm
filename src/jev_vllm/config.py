import json
import re
import math
from pathlib import Path
from urllib.parse import urlparse
from .parameters import initial_parameters, validate_parameters, request_parameters


def numeric(value, lo, hi, name, integer=False):
    if (
        type(value) not in (int, float)
        or not math.isfinite(value)
        or not lo <= value <= hi
        or (integer and type(value) is not int)
    ):
        raise ValueError(f"{name}: invalid value {value!r}")


def validate(c):
    g, s, p, e = c["generation"], c["sampling"], c["policy"], c["experiment"]

    if "backend" in g or "python" in c["paths"]:
        raise ValueError(
            "Remove generation.backend and paths.python; the active Python interpreter runs vLLM directly"
        )

    if any(
        key in p
        for key in (
            "rollback_drop",
            "stop_on_complete",
            "complete_min",
            "correct_min",
            "relevant_min",
        )
    ):
        raise ValueError(
            "Use policy.stopping and policy.rollback.score_drop (normalized 0-1 units)"
        )

    if e["mode"] not in ("adaptive", "fixed", "stop_only", "baseline"):
        raise ValueError("Unknown experiment mode")

    for name in ("chunk_tokens", "total_tokens", "max_rounds"):
        numeric(g[name], 1, 10000000, name, True)

    numeric(e["max_jev_calls"], 1, 1000000, "max_jev_calls", True)

    if not e["seeds"]:
        raise ValueError("Empty seeds")

    for seed in e["seeds"]:
        numeric(seed, 0, 2**31 - 1, "seed", True)

    validate_parameters(c["parameters"])
    request_parameters(s, c["parameters"])

    if any(name in p for name in ("error_max", "correctness_max", "relevance_max", "repetition_min")):
        raise ValueError("Score trigger thresholds are obsolete; typed Jev Choices now choose changes")

    if "rollback" in p or "cooldown_rounds" in p:
        raise ValueError(
            "policy.rollback and policy.cooldown_rounds were replaced by policy.revert "
            "(consecutive utility declines); remove them"
        )

    rv = p["revert"]
    if rv["rule"] not in ("consecutive_decrease", "below_best"):
        raise ValueError("policy.revert.rule must be consecutive_decrease or below_best")
    numeric(rv["consecutive_declines"], 1, 10000, "revert.consecutive_declines", True)
    numeric(p["limits"]["max_same_direction"], 0, 10000, "limits.max_same_direction", True)
    numeric(p["dormancy"]["keep_streak"], 0, 10000, "dormancy.keep_streak", True)
    numeric(p["dormancy"]["skip_rounds"], 0, 10000, "dormancy.skip_rounds", True)
    numeric(p["stopping"]["final_answer_tokens"], 1, 10000000, "stopping.final_answer_tokens", True)

    view = c["jev"]["view"]
    for name in ("keep_full", "head", "tail"):
        numeric(view[name], 0, 10000000, f"jev.view.{name}", True)

    for flag in (
        g["enable_thinking"],
        p["stopping"]["enabled"],
        rv["enabled"],
        view["score"],
        c["engine"]["enforce_eager"],
        c["runtime"]["use_flashinfer_sampler"],
    ):
        if type(flag) is not bool:
            raise ValueError("Expected boolean")

    for section in ("jev",):
        u = urlparse(c[section]["base_url"])

        if (
            u.scheme not in ("http", "https")
            or not u.netloc
            or u.username
            or u.password
        ):
            raise ValueError("Invalid base URL")

        numeric(c[section]["timeout_seconds"], 1, 3600, "timeout")

    if urlparse(c["jev"]["base_url"]).scheme != "https":
        raise ValueError("Jev requires HTTPS")

    numeric(c["engine"]["gpu_memory_utilization"], 0.01, 0.99, "GPU budget")

    for name in ("max_model_len", "max_num_seqs"):
        numeric(c["engine"][name], 1, 1000000, name, True)

    required = {"correctness", "relevance", "repetition", "completeness"}

    if set(c["jev"]["questions"]) != required or set(p["utility_weights"]) != required:
        raise ValueError("Policy requires four named score dimensions")

    for weight in p["utility_weights"].values():
        numeric(weight, 0, 1, "utility weight")

    if sum(p["utility_weights"].values()) <= 0:
        raise ValueError("At least one utility weight must be positive")

    for q in c["jev"]["questions"].values():
        if (
            q["type"] != "score"
            or not isinstance(q["criteria"], list)
            or not 2 <= len(q["criteria"]) <= 10
            or any(not isinstance(x, str) or not x.strip() for x in q["criteria"])
        ):
            raise ValueError("Invalid Score rubric")

    for dimension in ("completeness", "correctness", "relevance"):
        name = f"{dimension}_min"
        numeric(p["stopping"][name], 0, 1, f"policy.stopping.{name} (normalized score)")

    return c


def strip_line_comments(source):
    """Remove # comments while preserving JSON strings and line positions."""
    pattern = r'"(?:\\.|[^"\\])*"|#[^\r\n]*'

    return re.sub(
        pattern,
        lambda match: (
            " " * len(match.group()) if match.group().startswith("#") else match.group()
        ),
        source,
    )


def load_config(path):
    path = Path(path).resolve()
    c = json.loads(strip_line_comments(path.read_text(encoding="utf-8-sig")))

    if "sampling" in c or "bounds" in c["policy"]:
        raise ValueError("Define parameter values and bounds only in parameters.json")
    parameters_path = (path.parent / c["parameters_file"]).resolve()
    c["parameters_file"] = str(parameters_path)
    c["parameters"] = json.loads(
        strip_line_comments(parameters_path.read_text(encoding="utf-8-sig"))
    )
    validate_parameters(c["parameters"])
    c["sampling"] = initial_parameters(c["parameters"])

    if "questions" in c["jev"]:
        raise ValueError("Define rubrics in jev.questions_file, not inline questions")

    questions_path = (path.parent / c["jev"]["questions_file"]).resolve()
    c["jev"]["questions_file"] = str(questions_path)
    c["jev"]["questions"] = json.loads(
        strip_line_comments(questions_path.read_text(encoding="utf-8-sig"))
    )
    validate(c)

    for key, value in c["paths"].items():
        p = Path(value)
        c["paths"][key] = str((path.parent / p).resolve())

    return c
