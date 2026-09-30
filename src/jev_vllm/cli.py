import argparse
import json
from copy import deepcopy
from pathlib import Path

from .config import load_config
from .clients import JsonClient
from .backend import PythonBackend
from .parameters import check_backend_parameters, request_parameters
from .runner import load_tasks, run_experiment


def main():
    parser = argparse.ArgumentParser(description="Jev / vLLM research controller")
    parser.add_argument(
        "command", choices=["check", "doctor", "smoke", "run", "compare", "summarize"]
    )
    parser.add_argument(
        "--config", default=str(Path(__file__).resolve().parents[2] / "config.json")
    )
    args = parser.parse_args()

    c = load_config(args.config)
    tasks = load_tasks(c["paths"]["dataset"])

    if args.command == "check":
        print(
            f"Configuration valid; tasks={len(tasks)}; "
            "backend=python; "
            f"mode={c['experiment']['mode']}"
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

    key = c["jev"].get("api_key", "")

    if not isinstance(key, str) or not key.strip():
        raise ValueError("Set jev.api_key in config.json before running an experiment")
    key = key.strip()

    jev = JsonClient(c["jev"]["base_url"], c["jev"]["timeout_seconds"], key=key)
    modes = (
        ["fixed", "adaptive"]
        if args.command == "compare"
        else [c["experiment"]["mode"]]
    )
    cap = (
        len(tasks)
        * len(c["experiment"]["seeds"])
        * len(modes)
        * min(c["generation"]["max_rounds"], c["experiment"]["max_jev_calls"])
    )
    print(
        f"Tasks and generated text will be sent to Jev. "
        f"At most {cap} evaluation requests, "
        f'with {len(c["jev"]["questions"])} questions per request.',
        flush=True,
    )

    for task in tasks:
        for seed in c["experiment"]["seeds"]:
            for mode in modes:
                conf = deepcopy(c)
                conf["experiment"]["mode"] = mode

                if args.command == "compare":
                    conf["policy"]["stopping"]["enabled"] = False

                run_experiment(conf, task, seed, vllm, jev)

    return 0
