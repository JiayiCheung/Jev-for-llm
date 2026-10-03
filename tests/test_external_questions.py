import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from jev_vllm.config import load_config, strip_line_comments

ROOT = Path(__file__).resolve().parents[1]


class ExternalQuestionsTests(unittest.TestCase):
    def test_main_config_contains_only_rubric_reference(self):
        raw = json.loads(strip_line_comments((ROOT / "config.json").read_text()))
        self.assertNotIn("questions", raw["jev"])
        self.assertEqual(raw["jev"]["questions_file"], "jev_questions.json")

    def test_question_path_resolves_against_config_directory(self):
        raw = json.loads(strip_line_comments((ROOT / "config.json").read_text()))
        expected = load_config(ROOT / "config.json")["jev"]["questions"]
        raw["jev"].pop("questions", None)
        raw["jev"]["questions_file"] = "rubrics/custom.json"
        raw["parameters_file"] = str(ROOT / "parameters.json")

        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            (base / "rubrics").mkdir()
            (base / "rubrics/custom.json").write_text(
                "# External rubric\n" + json.dumps(expected), encoding="utf-8"
            )
            (base / "config.json").write_text(json.dumps(raw), encoding="utf-8")
            resolved = load_config(base / "config.json")
            self.assertEqual(resolved["jev"]["questions"], expected)
            self.assertEqual(
                resolved["jev"]["questions_file"],
                str((base / "rubrics/custom.json").resolve()),
            )


if __name__ == "__main__":
    unittest.main()
