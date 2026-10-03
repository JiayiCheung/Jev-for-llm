"""--task restricts run/compare to the named dataset task IDs."""

import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from jev_vllm.cli import main

CONFIG = str(Path(__file__).resolve().parents[1] / "config.json")


def run_check(*extra):
    out, err = io.StringIO(), io.StringIO()
    with patch.object(sys, "argv", ["run.py", "check", "--config", CONFIG, *extra]):
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                main()
                code = 0
            except SystemExit as exc:
                code = exc.code
    return code, out.getvalue(), err.getvalue()


class TaskFilterTests(unittest.TestCase):
    def test_check_rejects_task_filter_because_it_is_for_run_and_compare(self):
        code, _, err = run_check("--task", "gsm8k_train_01828")
        self.assertEqual(code, 2)
        self.assertIn("--task is available only for run or compare", err)

    def test_unknown_task_is_an_error(self):
        with patch.object(
            sys, "argv", ["run.py", "compare", "--config", CONFIG, "--task", "nope"]
        ):
            err = io.StringIO()
            with (
                contextlib.redirect_stderr(err),
                self.assertRaises(SystemExit) as raised,
            ):
                main()
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("Unknown task ID: nope", err.getvalue())


if __name__ == "__main__":
    unittest.main()
