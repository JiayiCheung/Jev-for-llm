import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from jev_vllm.config import strip_line_comments


class ConfigCommentTests(unittest.TestCase):
    def test_full_line_and_inline_comments(self):
        source = '# Header\n{\n"value": 42 # Inline\n}\n'
        self.assertEqual(json.loads(strip_line_comments(source)), {"value": 42})
        self.assertEqual(strip_line_comments(source).count("\n"), source.count("\n"))

    def test_strings_are_not_comments(self):
        expected = {
            "url": "https://example.com/a//b#fragment",
            "text": 'Say "hello" # text // literal',
            "path": "G:\\model\\",
        }
        source = json.dumps(expected) + " # End"
        self.assertEqual(json.loads(strip_line_comments(source)), expected)

    def test_invalid_json_is_still_rejected(self):
        with self.assertRaises(json.JSONDecodeError):
            json.loads(strip_line_comments('{"value": 1,} # Trailing comma'))


if __name__ == "__main__":
    unittest.main()
