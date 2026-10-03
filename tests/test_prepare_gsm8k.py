"""Sampling GSM8K tasks: reproducible, well-formed, and consistent with the shipped files."""

import hashlib
import json
import tempfile
import unittest
from importlib import util
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = util.spec_from_file_location(
    "prepare_gsm8k", ROOT / "scripts" / "prepare_gsm8k.py"
)
prepare = util.module_from_spec(spec)
spec.loader.exec_module(prepare)


def fake_rows(n=30):
    return [
        {"question": f"Question {i}?", "answer": f"step {i}\n#### {i * 10}"}
        for i in range(n)
    ]


class SamplingTests(unittest.TestCase):
    def test_sampling_is_reproducible_and_depends_on_the_seed(self):
        rows = fake_rows()
        first = prepare.sample_tasks(rows, "test", 8, seed=1)
        self.assertEqual(first, prepare.sample_tasks(rows, "test", 8, seed=1))
        self.assertNotEqual(first[0], prepare.sample_tasks(rows, "test", 8, seed=2)[0])
        self.assertEqual(len(set(first[0])), 8)  # without replacement

    def test_task_has_the_fields_the_runner_and_grader_use(self):
        task = prepare.make_task(
            "test", 7, {"question": "Q?", "answer": "work\n#### 1,250"}
        )
        self.assertEqual(task["id"], "gsm8k_test_00007")
        self.assertEqual(task["prompt"], "Q?")
        self.assertEqual(task["reference_answer"], "1,250")
        self.assertEqual(
            task["source"], {"dataset": "GSM8K", "split": "test", "row_index": 7}
        )

    def test_rows_without_a_final_answer_are_rejected(self):
        with self.assertRaises(ValueError):
            prepare.make_task("test", 0, {"question": "Q?", "answer": "no marker"})

    def test_count_must_fit_the_population(self):
        for count in (0, 31):
            with self.assertRaises(SystemExit):
                prepare.sample_tasks(fake_rows(), "test", count, seed=1)


class FileTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.tmp = Path(self.dir.name)
        raw = "".join(json.dumps(r) + "\n" for r in fake_rows()).encode("utf-8")
        (self.tmp / "gsm8k_test.jsonl").write_bytes(raw)
        self.raw_hash = hashlib.sha256(raw).hexdigest()

    def run_main(self, *extra):
        argv = [
            "--raw-dir",
            str(self.tmp),
            "--output",
            str(self.tmp / "tasks.jsonl"),
            "--manifest",
            str(self.tmp / "manifest.json"),
            "--count",
            "5",
            *extra,
        ]
        with patch.dict(prepare.KNOWN_SHA256, {"test": self.raw_hash}):
            prepare.main(argv)

    def test_main_writes_tasks_and_a_matching_manifest_twice_identically(self):
        self.run_main("--seed", "3")
        first = (self.tmp / "tasks.jsonl").read_bytes()
        manifest = json.loads((self.tmp / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["task_file_sha256"], hashlib.sha256(first).hexdigest()
        )
        self.assertEqual(manifest["sample_count"], 5)
        self.assertEqual(manifest["source_sha256"], self.raw_hash)
        self.run_main("--seed", "3")
        self.assertEqual((self.tmp / "tasks.jsonl").read_bytes(), first)

    def test_a_raw_file_that_is_not_the_original_is_refused(self):
        with self.assertRaises(SystemExit):
            prepare.main(
                [
                    "--raw-dir",
                    str(self.tmp),
                    "--output",
                    str(self.tmp / "t.jsonl"),
                    "--manifest",
                    str(self.tmp / "m.json"),
                ]
            )

    def test_a_missing_raw_file_is_not_downloaded_unless_asked(self):
        with self.assertRaises(SystemExit) as raised:
            prepare.load_benchmark("train", self.tmp, download=False)
        self.assertIn("--download", str(raised.exception))


class ShippedFilesTests(unittest.TestCase):
    def test_tasks_file_matches_its_manifest(self):
        tasks = (ROOT / "data" / "tasks.jsonl").read_bytes()
        manifest = json.loads(
            (ROOT / "data" / "gsm8k_sample_manifest.json").read_text(encoding="utf-8")
        )
        rows = [
            json.loads(line)
            for line in tasks.decode("utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(
            manifest["task_file_sha256"], hashlib.sha256(tasks).hexdigest()
        )
        self.assertEqual(manifest["sample_count"], len(rows))
        self.assertEqual(
            [r["source"]["row_index"] for r in rows], manifest["row_indices_zero_based"]
        )
        self.assertEqual(len({r["id"] for r in rows}), len(rows))


if __name__ == "__main__":
    unittest.main()
