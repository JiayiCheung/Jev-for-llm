"""Check configuration-only authentication and credential-free records."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from jev_vllm import cli
from jev_vllm.config import load_config
from jev_vllm.runner import run_experiment


class CredentialTests(unittest.TestCase):
    def test_record_redacts_key_without_changing_live_config(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {
                "paths": {"outputs": directory},
                "experiment": {"mode": "adaptive"},
                "jev": {"api_key": "test-secret-not-real"},
            }
            with patch("jev_vllm.runner.execute"):
                result = run_experiment(config, {"id": "test"}, 42, None, None)
            saved = next(Path(directory).glob("*/result.json")).read_text()
            self.assertNotIn("test-secret-not-real", saved)
            self.assertEqual(result["config"]["jev"]["api_key"], "[REDACTED]")
            self.assertEqual(config["jev"]["api_key"], "test-secret-not-real")

    def test_run_uses_config_key(self):
        config = load_config(Path(__file__).resolve().parents[1] / "config.json")
        config["jev"]["api_key"] = "test-secret-not-real"
        with (
            patch.object(sys, "argv", ["run.py", "run"]),
            patch.object(cli, "load_config", return_value=config),
            patch.object(
                cli, "load_tasks", return_value=[{"id": "test", "prompt": "test"}]
            ),
            patch.object(cli, "PythonBackend"),
            patch.object(cli, "check_backend_parameters"),
            patch.object(cli, "JsonClient") as client,
            patch.object(cli, "run_experiment"),
        ):
            self.assertEqual(cli.main(), 0)
            self.assertEqual(client.call_args.kwargs["key"], "test-secret-not-real")
