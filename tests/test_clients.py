import io
import sys
import unittest
from http.client import RemoteDisconnected
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from jev_vllm.clients import JsonClient


class SequenceOpener:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = 0

    def open(self, request, timeout):
        self.calls += 1
        item = next(self.responses)
        if isinstance(item, Exception):
            raise item
        return io.BytesIO(item)


def error(status, body=b"temporary"):
    return HTTPError(
        "https://example.test/score", status, "error", {}, io.BytesIO(body)
    )


class ClientRetryTests(unittest.TestCase):
    @patch("jev_vllm.clients.time.sleep")
    def test_remote_disconnect_retries_same_request(self, sleep):
        client = JsonClient("https://example.test", 5, key="secret")
        client.opener = SequenceOpener(
            [
                RemoteDisconnected("Remote end closed connection without response"),
                b'{"answers": {}}',
            ]
        )
        self.assertEqual(client.call("/score", {"state": "same"}), {"answers": {}})
        self.assertEqual(client.opener.calls, 2)
        sleep.assert_called_once_with(1)

    @patch("jev_vllm.clients.time.sleep")
    def test_remote_disconnect_stops_after_three_attempts(self, sleep):
        client = JsonClient("https://example.test", 5, key="secret")
        client.opener = SequenceOpener([RemoteDisconnected("closed") for _ in range(3)])
        with self.assertRaises(RemoteDisconnected):
            client.call("/score", {"state": "same"})
        self.assertEqual(client.opener.calls, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 3])

    @patch("jev_vllm.clients.time.sleep")
    def test_transient_http_520_retries_same_request(self, sleep):
        client = JsonClient("https://example.test", 5, key="secret")
        client.opener = SequenceOpener([error(520), b'{"answers": {}}'])
        self.assertEqual(client.call("/score", {"state": "same"}), {"answers": {}})
        self.assertEqual(client.opener.calls, 2)
        sleep.assert_called_once_with(1)

    @patch("jev_vllm.clients.time.sleep")
    def test_auth_error_does_not_retry_or_expose_key(self, sleep):
        client = JsonClient("https://example.test", 5, key="secret")
        client.opener = SequenceOpener([error(401, b"secret rejected")])
        with self.assertRaisesRegex(RuntimeError, r"HTTP 401: \[REDACTED\] rejected"):
            client.call("/score", {})
        self.assertEqual(client.opener.calls, 1)
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
