"""Transient connection drops are retried; timeouts and DNS failures are not."""

import io
import socket
import ssl
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from jev_vllm.clients import JsonClient, transient


class Opener:
    def __init__(self, items):
        self.items, self.calls = iter(items), 0

    def open(self, request, timeout):
        self.calls += 1
        item = next(self.items)
        if isinstance(item, Exception):
            raise item
        return io.BytesIO(item)


def tls_eof():
    return URLError(
        ssl.SSLError(
            8,
            "[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol",
        )
    )


class TransientErrorTests(unittest.TestCase):
    def client(self, items, **kwargs):
        client = JsonClient("https://example.test", 5, key="secret", **kwargs)
        client.opener = Opener(items)
        return client

    @patch("jev_vllm.clients.time.sleep")
    def test_tls_eof_is_retried_then_succeeds(self, sleep):
        client = self.client([tls_eof(), tls_eof(), b'{"answers": {}}'])
        self.assertEqual(client.call("/x", {}), {"answers": {}})
        self.assertEqual(client.opener.calls, 3)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [1, 3])

    @patch("jev_vllm.clients.time.sleep")
    def test_raw_ssl_error_and_connection_reset_are_retried(self, sleep):
        client = self.client(
            [ssl.SSLError("EOF"), ConnectionResetError("reset"), b"{}"]
        )
        self.assertEqual(client.call("/x", {}), {})
        self.assertEqual(client.opener.calls, 3)

    @patch("jev_vllm.clients.time.sleep")
    def test_gives_up_after_the_last_retry_and_raises_the_original_error(self, sleep):
        client = self.client([tls_eof() for _ in range(3)])
        with self.assertRaises(URLError):
            client.call("/x", {})
        self.assertEqual(client.opener.calls, 3)

    @patch("jev_vllm.clients.time.sleep")
    def test_timeouts_and_dns_failures_are_not_retried(self, sleep):
        for error in (
            URLError(TimeoutError("timed out")),
            URLError(socket.timeout("timed out")),
            ssl.SSLError("The read operation timed out"),
            URLError(socket.gaierror(11001, "getaddrinfo failed")),
        ):
            client = self.client([error, b"{}"])
            with self.assertRaises((URLError, OSError)):
                client.call("/x", {})
            self.assertEqual(client.opener.calls, 1, error)
        sleep.assert_not_called()

    @patch("jev_vllm.clients.time.sleep")
    def test_configured_delays_set_the_number_of_retries_and_the_waits(self, sleep):
        client = self.client(
            [tls_eof(), tls_eof(), tls_eof(), tls_eof(), b"{}"],
            retry_delays=[2, 5, 9, 30],
        )
        self.assertEqual(client.call("/x", {}), {})
        self.assertEqual(client.opener.calls, 5)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [2, 5, 9, 30])

    @patch("jev_vllm.clients.time.sleep")
    def test_empty_delays_mean_no_retry(self, sleep):
        client = self.client([tls_eof(), b"{}"], retry_delays=[])
        with self.assertRaises(URLError):
            client.call("/x", {})
        self.assertEqual(client.opener.calls, 1)
        sleep.assert_not_called()

    def test_shipped_config_retries_ten_times_with_growing_waits(self):
        from jev_vllm.config import load_config

        delays = load_config(Path(__file__).resolve().parents[1] / "config.json")[
            "jev"
        ]["retry_delays"]
        self.assertEqual(len(delays), 10)
        self.assertEqual(delays, sorted(set(delays)))  # strictly increasing
        self.assertEqual(sum(delays), 827)

    def test_transient_classifier(self):
        self.assertTrue(transient(tls_eof()))
        self.assertTrue(transient(ConnectionAbortedError()))
        self.assertFalse(transient(URLError(TimeoutError())))
        self.assertFalse(transient(ValueError("bad")))


if __name__ == "__main__":
    unittest.main()
