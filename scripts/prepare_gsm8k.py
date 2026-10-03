"""Sample GSM8K questions into data/tasks.jsonl (and a manifest that makes it reproducible).

Example:
    python scripts/prepare_gsm8k.py --split test --count 400 --seed 42

The raw benchmark file lives in data/raw/ (git-ignored). If it is missing, pass --download
to fetch it from the original repository; its SHA256 is checked against the known value.
"""

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from jev_vllm.runner import load_tasks  # noqa: E402

BASE_URL = (
    "https://raw.githubusercontent.com/openai/grade-school-math"
    "/master/grade_school_math/data"
)
# SHA256 of the original files, so that a download or a local copy can be verified.
KNOWN_SHA256 = {
    "train": "17f347dc51477c50d4efb83959dbb7c56297aba886e5544ee2aaed3024813465",
    "test": "3730d312f6e3440559ace48831e51066acaca737f6eabec99bccb9e4b3c39d14",
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def load_benchmark(split, raw_dir, download):
    """Return (rows, raw bytes, source url) of a GSM8K split, downloading it on request."""
    path = Path(raw_dir) / f"gsm8k_{split}.jsonl"
    url = f"{BASE_URL}/{split}.jsonl"
    if not path.exists():
        if not download:
            raise SystemExit(
                f"{path} is missing; run again with --download to fetch {url}"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        with urlopen(url, timeout=120) as response:
            path.write_bytes(response.read())
    raw = path.read_bytes()
    if sha256(raw) != KNOWN_SHA256[split]:
        raise SystemExit(
            f"{path} does not match the original GSM8K {split} file (SHA256)"
        )
    rows = [
        json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()
    ]
    return rows, raw, url


def make_task(split, index, row):
    """One task in the format the runner and the grader expect."""
    question, answer = row["question"], row["answer"]
    if not question.strip() or "####" not in answer:
        raise ValueError(f"GSM8K {split} row {index} has no question or no #### answer")
    return {
        "id": f"gsm8k_{split}_{index:05d}",
        "prompt": question,
        "reference": answer,
        "reference_answer": answer.rsplit("####", 1)[1].strip(),
        "source": {"dataset": "GSM8K", "split": split, "row_index": index},
    }


def sample_tasks(rows, split, count, seed):
    """`count` rows drawn without replacement with random.Random(seed), in drawn order."""
    if not 1 <= count <= len(rows):
        raise SystemExit(f"--count must be between 1 and {len(rows)}")
    indices = random.Random(seed).sample(range(len(rows)), count)
    return indices, [make_task(split, i, rows[i]) for i in indices]


def write_tasks(tasks, output):
    """Write the JSONL file atomically, checking it with the runner's own loader."""
    staged = Path(str(output) + ".pending")
    staged.write_text(
        "".join(json.dumps(task, ensure_ascii=True) + "\n" for task in tasks),
        encoding="utf-8",
    )
    loaded = load_tasks(staged)
    if len(loaded) != len(tasks) or len({t["prompt"] for t in loaded}) != len(tasks):
        raise SystemExit("the sampled tasks are not unique")
    staged.replace(output)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--split", choices=("train", "test"), default="test")
    parser.add_argument("--count", type=int, default=400)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--raw-dir", default=ROOT / "data" / "raw")
    parser.add_argument("--output", default=ROOT / "data" / "tasks.jsonl")
    parser.add_argument(
        "--manifest", default=ROOT / "data" / "gsm8k_sample_manifest.json"
    )
    parser.add_argument(
        "--download", action="store_true", help="fetch the raw file if absent"
    )
    args = parser.parse_args(argv)

    rows, raw, url = load_benchmark(args.split, args.raw_dir, args.download)
    indices, tasks = sample_tasks(rows, args.split, args.count, args.seed)
    output = Path(args.output)
    write_tasks(tasks, output)
    manifest = {
        "dataset": "GSM8K",
        "split": args.split,
        "source_url": url,
        "source_sha256": sha256(raw),
        "population_count": len(rows),
        "sample_count": len(tasks),
        "sampling_seed": args.seed,
        "sampling_method": f"Python random.Random({args.seed}).sample without replacement",
        "row_indices_zero_based": indices,
        "task_file_sha256": sha256(output.read_bytes()),
        "prompt_transform": "None; original English question retained",
    }
    Path(args.manifest).write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"{len(tasks)} {args.split} tasks written to {output}; manifest {args.manifest}"
    )


if __name__ == "__main__":
    main()
