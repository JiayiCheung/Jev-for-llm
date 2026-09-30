import json
import time
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import platform
import importlib.metadata
from .adapters import build_evaluation, parse_scores, score_response
from .policy import Controller
from .parameters import request_parameters, check_backend_parameters


def load_tasks(path):
    tasks = [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    ids = set()

    for t in tasks:
        if (
            not isinstance(t.get("id"), str)
            or not t["id"]
            or not isinstance(t.get("prompt"), str)
            or not t["prompt"].strip()
            or t["id"] in ids
        ):
            raise ValueError("Tasks require unique string id and nonempty prompt")

        ids.add(t["id"])

    if not tasks:
        raise ValueError("Empty dataset")

    return tasks


def execute(c, task, seed, vllm, jev, record, save):
    check_backend_parameters(vllm, c["parameters"])
    g = c["generation"]
    tok = vllm.tokenize(task["prompt"], g["enable_thinking"])
    prefix = tok["tokens"]

    if not prefix or any(type(i) is not int or i < 0 for i in prefix):
        raise ValueError("Invalid prompt tokens")

    record["prompt_token_count"] = len(prefix)
    ids, text = [], ""
    params = deepcopy(c["sampling"])
    ctl = Controller(c["policy"], c["parameters"], c["experiment"]["mode"])

    for step in range(g["max_rounds"]):
        room = min(
            g["chunk_tokens"],
            g["total_tokens"] - len(ids),
            tok["max_model_len"] - len(prefix) - len(ids),
        )

        if room <= 0:
            record["stop_reason"] = "token_or_context_budget"

            return

        if record["jev_calls"] >= c["experiment"]["max_jev_calls"]:
            record["stop_reason"] = "jev_call_budget"

            return

        row = {
            "step": step,
            "token_start": len(ids),
            "applied_parameters": deepcopy(params),
        }
        record["rounds"].append(row)
        request = {
            "prompt": prefix + ids,
            "max_tokens": room,
            **request_parameters(params, c["parameters"]),
            "seed": seed + step,
        }
        vllm.validate_parameters({k: v for k, v in request.items() if k != "prompt"})
        row["generation_request"] = request
        save()
        start = time.perf_counter()
        raw = vllm.generate(request)
        row.update(
            generation_response=raw, generation_seconds=time.perf_counter() - start
        )
        save()
        choice = raw["choices"][0]
        new = choice.get("token_ids")

        if (
            not isinstance(new, list)
            or len(new) > room
            or any(type(i) is not int or i < 0 for i in new)
        ):
            raise ValueError("Invalid generated token IDs")

        if choice.get("finish_reason") not in ("length", "stop"):
            raise ValueError("Unexpected finish reason")

        if not new:
            if choice["finish_reason"] == "stop":
                record["stop_reason"] = "model_stop"

                return

            raise ValueError("Empty generation")

        ids += new
        full = vllm.decode(ids)
        recent = full[len(text) :] if full.startswith(text) else choice["text"]
        text = full
        record.update(
            generated=text, generated_token_count=len(ids), generated_token_ids=ids
        )
        row["token_end"] = len(ids)
        evaluation = build_evaluation(task["prompt"], text, recent, step, c["jev"])
        row["evaluation_request"] = evaluation
        record["jev_calls"] += 1
        save()
        start = time.perf_counter()
        response = score_response(jev.call(c["jev"]["endpoint"], evaluation))
        row.update(
            evaluation_response=response, evaluation_seconds=time.perf_counter() - start
        )
        save()
        scores = parse_scores(response, c["jev"]["questions"])
        row["scores"] = scores
        decision = ctl.decide(scores, params, step)
        row["decision"] = decision
        # A proposal is not an executed parameter change. Next row records actual request parameters.
        row["decision_will_execute"] = False
        reason = None

        if choice["finish_reason"] == "stop":
            reason = "model_stop"
        elif decision["stop"]:
            reason = "score_complete"
        elif len(ids) >= g["total_tokens"]:
            reason = "token_budget"
        elif len(prefix) + len(ids) >= tok["max_model_len"]:
            reason = "context_budget"
        elif step + 1 >= g["max_rounds"]:
            reason = "round_budget"
        elif record["jev_calls"] >= c["experiment"]["max_jev_calls"]:
            reason = "jev_call_budget"

        print(
            f"[{task['id']} seed={seed} {c['experiment']['mode']}] Chunk {step+1}: {decision['action']} / {decision['reason']}",
            flush=True,
        )

        if reason:
            record["stop_reason"] = reason
            save()

            return

        params = deepcopy(decision["parameters"])
        row["decision_will_execute"] = True
        save()


def run_experiment(c, task, seed, vllm, jev):
    directory = Path(c["paths"]["outputs"]) / (
        datetime.now().strftime("%Y%m%d_%H%M%S_%f") + "_" + c["experiment"]["mode"]
    )
    directory.mkdir(parents=True, exist_ok=False)
    recorded_config = deepcopy(c)
    recorded_config["jev"]["api_key"] = "[REDACTED]"
    record = {
        "status": "running",
        "config": recorded_config,
        "task": task,
        "seed": seed,
        "rounds": [],
        "jev_calls": 0,
        "generated_token_count": 0,
    }
    record["environment"] = {
        "python": platform.python_version(),
        "platform": platform.platform(),
    }

    for name in ("vllm", "torch", "transformers"):
        try:
            record["environment"][name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            record["environment"][name] = "not_installed_in_client"

    start = time.perf_counter()

    def save():
        record["elapsed_seconds"] = time.perf_counter() - start
        tmp = directory / "result.tmp"
        tmp.write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp.replace(directory / "result.json")
        (directory / "answer.txt").write_text(
            record.get("generated", ""), encoding="utf-8"
        )

    try:
        save()
        execute(c, task, seed, vllm, jev, record, save)
        record["status"] = "completed"
    except BaseException as exc:
        record["status"] = (
            "interrupted" if isinstance(exc, KeyboardInterrupt) else "error"
        )
        message = f"{type(exc).__name__}: {exc}"
        key = getattr(jev, "key", None)
        record["error"] = message.replace(key, "[REDACTED]") if key else message
        raise
    finally:
        save()
        print("Results:", directory)

    return record
