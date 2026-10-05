"""Command-line entry point: check, preview, doctor, smoke, run, compare, ..."""

import argparse
import hashlib
import json
import os
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .backend import PythonBackend
from .clients import JsonClient
from .config import load_config
from .jev_requests import direction_request, score_request, value_request
from .parameters import check_backend_parameters, request_parameters
from .runner import load_tasks, run_batch
from .signals import build as build_signals


def main():
    """Parse the command line, run the chosen command and return the exit code."""
    parser = argparse.ArgumentParser(description="Jev / vLLM research controller")
    parser.add_argument(
        "command",
        choices=[
            "check",
            "preview",
            "doctor",
            "smoke",
            "run",
            "compare",
            "summarize",
            "dashboard",
        ],
    )
    parser.add_argument(
        "--config", default=str(Path(__file__).resolve().parents[2] / "config.json")
    )
    parser.add_argument(
        "--start-task",
        help="For run/compare, begin at this dataset task ID (inclusive).",
    )
    parser.add_argument(
        "--task",
        action="append",
        help="For run/compare, run only this dataset task ID (repeatable).",
    )
    parser.add_argument(
        "--experiment-id",
        help="Batch ID for run/compare; generated automatically when omitted.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="With --experiment-id, skip completed runs in the same batch.",
    )
    parser.add_argument(
        "--mode",
        choices=["baseline", "fixed", "adaptive"],
        help="Override the mode for a single `run` batch.",
    )
    parser.add_argument(
        "--baseline-compare-dir",
        type=Path,
        help="Baseline/adaptive paired report for dashboard.",
    )
    parser.add_argument(
        "--fixed-compare-dir",
        type=Path,
        help="Fixed/adaptive paired report for dashboard.",
    )
    parser.add_argument(
        "--dashboard-dir", type=Path, help="Directory for generated dashboard files."
    )
    parser.add_argument(
        "--analysis-dir", type=Path, help="Search this directory for paired reports."
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="Dashboard localhost port (0 selects a free port).",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Print dashboard URL without opening a browser.",
    )
    args = parser.parse_args()
    if args.experiment_id and (
        args.command not in ("run", "compare")
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", args.experiment_id)
    ):
        parser.error(
            "--experiment-id is only for run/compare and must be a safe ID (1–80 characters)"
        )
    if args.resume and args.command not in ("run", "compare"):
        parser.error("--resume is only for run/compare")
    if args.mode and args.command != "run":
        parser.error("--mode is only available for run")
    if args.command == "dashboard":
        if not 0 <= args.port <= 65535:
            parser.error("--port must be between 0 and 65535")
        from .dashboard import launch_dashboard

        return launch_dashboard(
            Path(__file__).resolve().parents[2],
            baseline_dir=args.baseline_compare_dir,
            fixed_dir=args.fixed_compare_dir,
            output_dir=args.dashboard_dir,
            analysis_dir=args.analysis_dir,
            port=args.port,
            open_browser=not args.no_browser,
        )

    c = load_config(args.config)
    if args.mode:
        c["experiment"]["mode"] = args.mode
    tasks = load_tasks(c["paths"]["dataset"])
    if args.task:
        if args.command not in ("run", "compare"):
            parser.error("--task is available only for run or compare")
        unknown = sorted(set(args.task) - {task["id"] for task in tasks})
        if unknown:
            parser.error(f"Unknown task ID: {', '.join(unknown)}")
        tasks = [task for task in tasks if task["id"] in args.task]
    if args.start_task:
        if args.command not in ("run", "compare"):
            parser.error("--start-task is available only for run or compare")
        start = next(
            (i for i, task in enumerate(tasks) if task["id"] == args.start_task), None
        )
        if start is None:
            parser.error(f"Unknown task ID: {args.start_task}")
        tasks = tasks[start:]

    if args.command == "check":
        print(
            f"Configuration valid; tasks={len(tasks)}; "
            "backend=python; "
            f"mode={c['experiment']['mode']}"
        )

        return 0

    if args.command == "preview":
        task = tasks[0]["prompt"]
        generated = "Illustrative partial answer for request-shape inspection."
        scores = {
            name: {"normalized": 0.5, "p_severe": 0.1} for name in c["jev"]["questions"]
        }
        rows = [{"step": 0, "applied_parameters": c["sampling"], "scores": scores}]
        signals = build_signals(rows, c, c["parameters"])
        threshold = c["policy"]["signals"]["persistence_threshold"]
        directions, offered = direction_request(
            task,
            generated,
            0,
            signals,
            c["sampling"],
            c["parameters"],
            c["jev"],
            threshold,
        )
        selected = {qid: "keep" for qid in offered}
        numeric = next((qid for qid in offered if qid == "direction_temperature"), None)
        if numeric:
            selected[numeric] = "increase"
        values, _, _ = value_request(
            task,
            generated,
            0,
            signals,
            c["sampling"],
            selected,
            offered,
            c["jev"],
            threshold,
        )
        print(
            json.dumps(
                {
                    "note": "Offline illustrative JSON only; no model or Jev call was made.",
                    "score_request": score_request(task, [generated], c["jev"]),
                    "direction_request": directions,
                    "value_request": values,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "summarize":
        for path in sorted(Path(c["paths"]["outputs"]).glob("*/result.json")):
            r = json.loads(path.read_text(encoding="utf-8"))
            print(
                json.dumps(
                    {
                        "task": r["task"]["id"],
                        "seed": r["seed"],
                        "mode": r["config"]["experiment"]["mode"],
                        "status": r["status"],
                        "stop": r.get("stop_reason"),
                        "tokens": r["generated_token_count"],
                        "jev_calls": r["jev_calls"],
                        "seconds": round(r["elapsed_seconds"], 3),
                        "result": str(path),
                    },
                    ensure_ascii=False,
                )
            )

        return 0

    vllm = PythonBackend(c)
    check_backend_parameters(vllm, c["parameters"])

    if args.command == "doctor":
        print("Native SamplingParams validated. No model loaded and no Jev call made.")
        return 0

    if args.command == "smoke":
        tok = vllm.tokenize(tasks[0]["prompt"], c["generation"]["enable_thinking"])
        result = vllm.generate(
            {
                "prompt": tok["tokens"],
                "max_tokens": 8,
                **request_parameters(c["sampling"], c["parameters"]),
                "seed": c["experiment"]["seeds"][0],
            }
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    key = c["jev"].get("api_key") or os.environ.get("TYPESAFE_API_KEY", "")

    if c["experiment"]["mode"] != "baseline" and (
        not isinstance(key, str) or not key.strip()
    ):
        raise ValueError("Set jev.api_key in config.json before running an experiment")
    key = key.strip() if isinstance(key, str) else ""
    c["jev"]["api_key"] = key

    jev = (
        None
        if c["experiment"]["mode"] == "baseline"
        else JsonClient(
            c["jev"]["base_url"],
            c["jev"]["timeout_seconds"],
            key=key,
            retry_delays=c["jev"]["retry_delays"],
        )
    )
    modes = (
        ["fixed", "adaptive"]
        if args.command == "compare"
        else [c["experiment"]["mode"]]
    )
    if modes == ["baseline"]:
        print("Baseline generates locally without Jev requests.", flush=True)
    else:
        print(
            "Tasks and generated text will be sent to Jev. "
            "Each run ends when the model stops or the context window is "
            "full; there is no request cap. "
            "fixed uses one Score request per segment, adaptive can add "
            "direction and value Choice requests.",
            flush=True,
        )

    manifest_dir = Path(c["paths"]["outputs"]) / "experiments"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    comparable_config = deepcopy(c)
    comparable_config["jev"].pop("api_key", None)
    comparable_config["jev"].pop(
        "retry_delays", None
    )  # transport setting, not an experimental condition
    comparable_config["experiment"].pop("mode", None)
    comparable_config["experiment"].pop("seeds", None)
    comparable_config["experiment"].pop(
        "max_consecutive_errors", None
    )  # how to react, not what to run
    comparable_config["paths"].pop("outputs", None)
    condition_hash = hashlib.sha256(
        json.dumps(
            comparable_config, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    manifest = {
        "id": None,
        "command": args.command,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "task_ids": [task["id"] for task in tasks],
        "task_hashes": {
            task["id"]: hashlib.sha256(
                json.dumps(
                    task, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            ).hexdigest()
            for task in tasks
        },
        "seeds": c["experiment"]["seeds"],
        "modes": modes,
        "planned_runs": len(tasks) * len(c["experiment"]["seeds"]) * len(modes),
        "condition_hash": condition_hash,
    }
    plan_keys = (
        "command",
        "task_ids",
        "task_hashes",
        "seeds",
        "modes",
        "planned_runs",
        "condition_hash",
    )
    experiment_id = args.experiment_id
    if args.resume and not experiment_id:
        # "python run.py compare --resume": continue the most recent batch with this exact plan
        matching = []
        for path in manifest_dir.glob("*.json"):
            try:
                prior = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if all(prior.get(k) == manifest[k] for k in plan_keys):
                matching.append((prior.get("created_utc", ""), prior["id"]))
        if not matching:
            raise ValueError(
                "--resume found no earlier batch with the same command, tasks, seeds, modes "
                "and configuration; start one without --resume, or give --experiment-id"
            )
        experiment_id = max(matching)[1]
        print(f"Resuming the most recent matching batch: {experiment_id}", flush=True)
    experiment_id = (
        experiment_id
        or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    )
    manifest["id"] = experiment_id
    manifest_path = manifest_dir / f"{experiment_id}.json"
    if manifest_path.exists():
        if not args.resume:
            raise ValueError(
                f"Experiment ID already exists; use --resume to continue: {experiment_id}"
            )
        prior = json.loads(manifest_path.read_text(encoding="utf-8"))
        if any(prior.get(k) != manifest[k] for k in plan_keys):
            raise ValueError(
                f"Existing experiment ID has a different plan: {experiment_id}"
            )
    else:
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(f"Experiment ID: {experiment_id}", flush=True)
    print(
        "If this run is interrupted, continue it with: python run.py "
        f"{args.command} --resume   (or add --experiment-id {experiment_id})",
        flush=True,
    )
    completed, unfinished = set(), 0
    if args.resume:
        for path in Path(c["paths"]["outputs"]).rglob("result.json"):
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
            except (
                ValueError
            ):  # a record cut off by a crash: that run is simply not complete
                unfinished += 1
                continue
            if (item.get("experiment") or {}).get("id") != experiment_id:
                continue
            if item.get("status") != "completed":
                unfinished += 1
                continue
            key = (
                item["task"]["id"],
                item["seed"],
                item["config"]["experiment"]["mode"],
            )
            if key in completed:
                raise ValueError(f"Duplicate completed run in batch: {key}")
            completed.add(key)
        print(
            f"Resume: {len(completed)} of {manifest['planned_runs']} runs are complete and "
            f"will be skipped; {unfinished} unfinished earlier attempt(s) are ignored "
            "and those runs start again from their first segment",
            flush=True,
        )

    failures = run_batch(
        c,
        tasks,
        modes,
        vllm,
        jev,
        experiment_id,
        args.command,
        completed,
        c["experiment"].get("max_consecutive_errors", 3),
    )

    if failures:
        print(f"{len(failures)} run(s) failed:", flush=True)
        for failure in failures:
            print(
                f"  {failure['task']} seed={failure['seed']} {failure['mode']}: "
                f"{failure['error']}",
                flush=True,
            )
        print(
            f"To retry only what is missing: run the same command with "
            f"--experiment-id {experiment_id} --resume",
            flush=True,
        )

        return 1

    return 0
