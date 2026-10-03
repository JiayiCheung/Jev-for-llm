"""One experiment run: generation, Jev scoring, control, restarts and the record."""

import importlib.metadata
import json
import platform
import sys
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from .adapters import choice_response, parse_scores, score_response
from .jev_requests import (
    checkpoint_request,
    chosen_values,
    difference_request,
    direction_request,
    evaluation_view,
    objective,
    parse_choices,
    score_request,
    value_request,
)
from .parameters import check_backend_parameters, request_parameters
from .policy import Controller


def write_file(path, text):
    """Write `text` to `path`, surviving a file that another program briefly holds open.

    On Windows the rename (or a plain write) fails with PermissionError while an antivirus
    scan, the search indexer or an editor has the file open. A long run must not die of
    that: retry with a growing pause (about 25 s in all) and, if the file stays locked,
    warn and carry on, because the next save rewrites it anyway. Returns True on success.
    """
    tmp = path.with_name(path.name + ".tmp")
    for attempt in range(50):
        try:
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(path)
            return True
        except PermissionError:
            time.sleep(min(0.02 * 2**attempt, 0.5))
    print(
        f"Warning: {path} stayed locked; it will be written at the next save.",
        file=sys.stderr,
        flush=True,
    )
    return False


def load_tasks(path):
    """Read the JSONL task file; each task needs a unique string id and a non-empty prompt."""
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
    """Run one task with one seed in the configured mode, saving every step to `record`."""
    check_backend_parameters(vllm, c["parameters"])
    g = c["generation"]
    tok = vllm.tokenize(task["prompt"], g["enable_thinking"])
    prefix = tok["tokens"]

    if not prefix or any(type(i) is not int or i < 0 for i in prefix):
        raise ValueError("Invalid prompt tokens")

    record["prompt_token_count"] = len(prefix)
    record.setdefault("total_generated_tokens", 0)
    record.setdefault("wasted_tokens", 0)
    record.setdefault("restarts", [])
    view_cfg = c["jev"]["view"]
    goal = objective(c["policy"]["utility_weights"])
    mode = c["experiment"]["mode"]
    baseline = mode == "baseline"
    rcfg = c["policy"]["restart"]
    restart_on = rcfg["enabled"] and not baseline

    # Everything that belongs to the trajectory being generated now; a restart rewinds it.
    s = SimpleNamespace(
        ids=[],
        text="",
        segments=[],
        rows=[],
        epoch=0,
        params=deepcopy(c["sampling"]),
        ctl=None if baseline else Controller(c["policy"], c["parameters"], mode),
        marks=[{"round": 0, "tokens": 0, "correctness": None}],
        next_check=rcfg["first_check_round"],
    )

    def sync():
        """Mirror the current attempt into the record and update the wasted-token count."""
        record.update(
            generated=s.text,
            generated_token_count=len(s.ids),
            generated_token_ids=s.ids,
            wasted_tokens=record["total_generated_tokens"] - len(s.ids),
        )

    def generate_round():
        """One segment with the current parameters.

        Returns None when the context is full, (row, choice, None) when the model ended with an
        empty segment, otherwise (row, choice, text of the new segment)."""
        step = len(s.rows)
        room = min(g["chunk_tokens"], tok["max_model_len"] - len(prefix) - len(s.ids))

        if room <= 0:
            return None

        row = {
            "step": step,
            "epoch": s.epoch,
            "token_start": len(s.ids),
            "applied_parameters": deepcopy(s.params),
        }
        record["rounds"].append(row)
        s.rows.append(row)
        request = {
            "prompt": prefix + s.ids,
            "max_tokens": room,
            **request_parameters(s.params, c["parameters"]),
            "seed": seed + step + 1000 * s.epoch,
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

        # "repetition": vLLM cut the segment because it detected a loop; the run goes on.
        if choice.get("finish_reason") not in ("length", "stop", "repetition"):
            raise ValueError("Unexpected finish reason")

        if not new:
            if choice["finish_reason"] == "stop":
                return row, choice, None

            raise ValueError("Empty generation")

        s.ids += new
        record["total_generated_tokens"] += len(new)
        full = vllm.decode(s.ids)
        recent = full[len(s.text) :] if full.startswith(s.text) else choice["text"]
        s.text = full
        s.segments.append(recent)
        sync()
        row["token_end"] = len(s.ids)
        row["answer_snapshot"] = s.text
        return row, choice, recent

    def ask(row, stem, request):
        """One Choice request to Jev, recorded on `row` under `stem`_request/_response/_seconds."""
        row[stem + "_request"] = request
        record["jev_calls"] += 1
        save()
        start = time.perf_counter()
        raw = jev.call(c["jev"]["endpoint"], request)
        row[stem + "_response"] = choice_response(raw)
        row[stem + "_seconds"] = time.perf_counter() - start
        save()
        return raw

    def ask_checkpoint(row, step, view, recent, scores):
        """Ask Jev to continue or go back; returns (option, its mark or None, probabilities)."""
        trace = [
            {
                "round": r["step"] + 1,
                **{k: round(v["normalized"], 3) for k, v in r["scores"].items()},
            }
            for r in s.rows
            if "scores" in r
        ]
        request, options = checkpoint_request(
            task["prompt"], view, recent, step, scores, s.marks, trace, c["jev"]
        )
        raw = ask(row, "checkpoint", request)
        picked = parse_choices(raw, request["questions"])["restart_point"]
        row["checkpoint_choice"] = picked
        return picked, options[picked], raw["answers"]["restart_point"]["probabilities"]

    def restart_from(mark, at_round, picked, probabilities, row):
        """Rewind to `mark`, then generate fresh attempts until Jev finds one that takes a different
        approach (at most difference.max_tries). Returns True when the run ended meanwhile.
        """
        k = mark["round"]
        event = {
            "at_round": at_round,
            "choice": picked,
            "mark_round": k,
            "probabilities": probabilities,
            "tries": [],
        }
        record["restarts"].append(event)
        row["restart"] = event
        failed = list(s.segments[k:])
        resume_params = deepcopy(s.rows[k]["applied_parameters"])
        diff = rcfg["difference"]

        for _ in range(diff["max_tries"]):
            for r in s.rows[k:]:
                r["abandoned"] = True
            s.epoch += 1
            s.ids = s.ids[: mark["tokens"]]
            s.text = vllm.decode(s.ids) if s.ids else ""
            s.segments = s.segments[:k]
            s.rows = s.rows[:k]
            s.params = deepcopy(resume_params)
            s.ctl = Controller(c["policy"], c["parameters"], mode)
            sync()
            save()

            for _ in range(diff["probe_rounds"]):
                out = generate_round()

                if out is None:
                    record["stop_reason"] = "context_budget"
                    event["accepted"] = "context_full"
                    return True

                probe, choice, recent = out
                probe["probe"] = True

                if recent is None or choice["finish_reason"] == "stop":
                    record["stop_reason"] = "model_stop"
                    event["accepted"] = "model_stop"
                    return True

            request = difference_request(
                task["prompt"],
                "".join(failed[: diff["probe_rounds"]]),
                "".join(s.segments[k:]),
                c["jev"],
            )
            raw = ask(probe, "difference", request)
            verdict = parse_choices(raw, request["questions"])["approach"]
            event["tries"].append(
                {
                    "epoch": s.epoch,
                    "verdict": verdict,
                    "probabilities": raw["answers"]["approach"]["probabilities"],
                }
            )

            if verdict == "different_approach":
                event["accepted"] = "different"
                break
        else:
            event["accepted"] = "max_tries"

        s.marks = [m for m in s.marks if m["round"] <= k]
        s.next_check = max(
            rcfg["first_check_round"] if k == 0 else k + rcfg["recheck_every"],
            len(s.rows) + 1,
        )
        save()
        return False

    while True:
        out = generate_round()

        if out is None:
            record["stop_reason"] = "context_budget"

            return

        row, choice, recent = out

        # An empty segment that ends with `stop` means the model had already finished.
        if recent is None:
            record["stop_reason"] = "model_stop"

            return

        step = row["step"]

        if baseline:
            if choice["finish_reason"] == "stop":
                record["stop_reason"] = "model_stop"
            elif len(prefix) + len(s.ids) >= tok["max_model_len"]:
                record["stop_reason"] = "context_budget"
            save()
            if record.get("stop_reason"):
                return
            continue
        # Score the new segment with Jev: one request, four rubrics.
        view = evaluation_view(
            s.segments, view_cfg["keep_full"], view_cfg["head"], view_cfg["tail"]
        )
        evaluation = score_request(
            task["prompt"],
            view if view_cfg["score"] else s.text,
            recent,
            step,
            c["jev"],
        )
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
        decision = s.ctl.decide(scores, s.params, step)
        # A proposal is not an executed change: the next row records the parameters actually used.
        row["decision_will_execute"] = False
        reason = None

        if choice["finish_reason"] == "stop":
            reason = "model_stop"
        elif len(prefix) + len(s.ids) >= tok["max_model_len"]:
            reason = "context_budget"

        # From round `first_check_round` Jev may send the reasoning back to a checkpoint.
        if (
            reason is None
            and restart_on
            and len(s.rows) >= s.next_check
            and len(record["restarts"]) < rcfg["max_restarts"]
        ):
            picked, mark, probabilities = ask_checkpoint(
                row, step, view, recent, scores
            )

            if mark is None:
                s.marks.append(
                    {
                        "round": len(s.rows),
                        "tokens": len(s.ids),
                        "correctness": scores["correctness"]["normalized"],
                    }
                )
                s.next_check = len(s.rows) + rcfg["recheck_every"]
            else:
                row["decision"] = decision
                ended = restart_from(mark, len(s.rows), picked, probabilities, row)
                print(
                    f"[{task['id']} seed={seed} {mode}] Chunk {step+1}: restart / {picked} "
                    f"({record['restarts'][-1]['accepted']})",
                    flush=True,
                )

                if ended:
                    save()

                    return

                continue

        # Adaptive mode: Jev picks a direction and an exact value for each parameter.
        if reason is None and decision["reason"] == "choice_ready":
            request_choice, offered = direction_request(
                task["prompt"],
                view,
                recent,
                step,
                scores,
                s.params,
                s.ctl.active_specs(step),
                c["jev"],
                s.ctl.blocked(),
                goal,
            )
            if request_choice is not None:
                raw_choice = ask(row, "direction", request_choice)
                selected = parse_choices(raw_choice, request_choice["questions"])
                s.ctl.note_directions(
                    {offered[q]["name"]: d for q, d in selected.items()}, step
                )
                exact_request, exact, immediate = value_request(
                    task["prompt"],
                    view,
                    recent,
                    step,
                    scores,
                    s.params,
                    selected,
                    offered,
                    c["jev"],
                    goal,
                )
                changes = immediate
                if exact_request is not None:
                    raw_value = ask(row, "value", exact_request)
                    changes.update(chosen_values(raw_value, exact_request, exact))
                decision = s.ctl.commit(decision, s.params, changes, step)

        row["decision"] = decision

        print(
            f"[{task['id']} seed={seed} {mode}] Chunk {step+1}: "
            f"{decision['action']} / {decision['reason']}",
            flush=True,
        )

        if reason:
            record["stop_reason"] = reason
            save()

            return

        s.params = deepcopy(decision["parameters"])
        row["decision_will_execute"] = True
        save()


def run_experiment(c, task, seed, vllm, jev, experiment=None):
    """Create the result folder, run `execute` and always leave a saved record behind."""
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
        "total_generated_tokens": 0,
        "wasted_tokens": 0,
        "restarts": [],
    }
    if experiment is not None:
        record["experiment"] = {
            **experiment,
            "started_utc": datetime.now(timezone.utc).isoformat(),
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
        """Write result.json atomically and rewrite answer.txt (abandoned rounds left out)."""
        record["elapsed_seconds"] = time.perf_counter() - start
        write_file(
            directory / "result.json", json.dumps(record, ensure_ascii=False, indent=2)
        )
        answers = [
            f"=== Round {row['step'] + 1} | cumulative generated tokens: {row['token_end']} ===\n"
            f"{row['answer_snapshot']}"
            for row in record["rounds"]
            if "answer_snapshot" in row and not row.get("abandoned")
        ]
        write_file(
            directory / "answer.txt", "\n\n".join(answers) + ("\n" if answers else "")
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
