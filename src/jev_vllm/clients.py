"""HTTPS client for the Jev API; retries dropped connections."""

import json
import ssl
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener


def transient(exc):
    """Connection drops worth retrying (TLS EOF, reset). Timeouts are excluded: the
    server may already have processed the request and a retry would be paid twice."""
    reason = getattr(exc, "reason", exc)
    if isinstance(reason, TimeoutError) or "timed out" in str(reason):
        return False
    return isinstance(reason, (ssl.SSLError, ConnectionError))


class JsonClient:
    """POST JSON to the Jev API with Bearer authentication, retrying transient failures."""

    def __init__(self, base, timeout, key=None, retry_delays=(1, 3)):
        self.base, self.timeout, self.key = base.rstrip("/"), timeout, key
        self.retry_delays = tuple(
            retry_delays
        )  # seconds before each retry; its length is the retry count
        self.opener = build_opener()

    def call(self, route, payload=None):
        """POST `payload` to `route` and return the JSON; the key is redacted in errors."""
        headers = {"Content-Type": "application/json"}

        if self.key:
            headers["Authorization"] = "Bearer " + self.key

        body = (
            None
            if payload is None
            else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        )
        retries = len(self.retry_delays)
        for attempt in range(retries + 1):
            try:
                with self.opener.open(
                    Request(self.base + route, data=body, headers=headers),
                    timeout=self.timeout,
                ) as r:
                    return json.load(r)
            except HTTPError as exc:
                text = exc.read().decode("utf-8", errors="replace")
                if self.key:
                    text = text.replace(self.key, "[REDACTED]")
                if (
                    exc.code in {500, 502, 503, 504, 520, 522, 524}
                    and attempt < retries
                ):
                    time.sleep(self.retry_delays[attempt])
                    continue
                raise RuntimeError(f"HTTP {exc.code}: {text}") from None
            except (
                URLError,
                ssl.SSLError,
                ConnectionError,
            ) as exc:  # HTTPError is handled above
                if transient(exc) and attempt < retries:
                    time.sleep(self.retry_delays[attempt])
                    continue
                raise
