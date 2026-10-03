"""A file briefly locked by another program must not kill a long run."""

import io
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import tempfile

from jev_vllm.runner import write_file


def flaky_replace(failures):
    """A Path.replace that raises PermissionError for the first `failures` calls."""
    state = {"calls": 0, "real": Path.replace}

    def replace(path, target):
        state["calls"] += 1
        if state["calls"] <= failures:
            raise PermissionError(5, "Access is denied")
        return state["real"](path, target)

    replace.state = state
    return replace


@patch("jev_vllm.runner.time.sleep")
class WriteFileTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "result.json"
        self.addCleanup(self.dir.cleanup)

    def test_plain_write_replaces_the_file_and_leaves_no_temp_file(self, sleep):
        self.path.write_text("old", encoding="utf-8")
        self.assertTrue(write_file(self.path, "new"))
        self.assertEqual(self.path.read_text(encoding="utf-8"), "new")
        self.assertEqual(
            [p.name for p in Path(self.dir.name).iterdir()], ["result.json"]
        )
        sleep.assert_not_called()

    def test_a_brief_lock_is_retried_until_it_clears(self, sleep):
        flaky = flaky_replace(5)
        with patch.object(Path, "replace", flaky):
            self.assertTrue(write_file(self.path, "payload"))
        self.assertEqual(flaky.state["calls"], 6)
        self.assertEqual(self.path.read_text(encoding="utf-8"), "payload")
        self.assertEqual(sleep.call_count, 5)

    def test_pauses_grow_but_are_capped(self, sleep):
        with patch.object(Path, "replace", flaky_replace(12)):
            write_file(self.path, "x")
        pauses = [c.args[0] for c in sleep.call_args_list]
        self.assertEqual(pauses, sorted(pauses))
        self.assertLessEqual(max(pauses), 0.5)

    def test_a_lock_that_never_clears_warns_and_does_not_raise(self, sleep):
        self.path.write_text("old", encoding="utf-8")
        err = io.StringIO()
        with (
            patch.object(Path, "replace", flaky_replace(10**6)),
            redirect_stderr(err),
        ):
            self.assertFalse(write_file(self.path, "new"))
        self.assertEqual(
            self.path.read_text(encoding="utf-8"), "old"
        )  # the old copy survives
        self.assertIn("stayed locked", err.getvalue())

    def test_a_locked_temp_file_is_retried_too(self, sleep):
        real = Path.write_text
        calls = {"n": 0}

        def write_text(path, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] <= 2:
                raise PermissionError(5, "Access is denied")
            return real(path, *args, **kwargs)

        with patch.object(Path, "write_text", write_text):
            self.assertTrue(write_file(self.path, "ok"))
        self.assertEqual(self.path.read_text(encoding="utf-8"), "ok")


if __name__ == "__main__":
    unittest.main()
