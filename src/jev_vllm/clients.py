import json
import time
from http.client import RemoteDisconnected
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError


class JsonClient:
    def __init__(self, base, timeout, key=None, local=False):
        self.base, self.timeout, self.key = base.rstrip("/"), timeout, key
        self.opener = build_opener(ProxyHandler({})) if local else build_opener()
        self.last_seconds = 0

    def call(self, route, payload=None):
        headers = {"Content-Type": "application/json"}

        if self.key:
            headers["Authorization"] = "Bearer " + self.key

        body = (
            None
            if payload is None
            else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        )
        start = time.perf_counter()

        try:
            for attempt in range(3):
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
                    if exc.code in {500, 502, 503, 504, 520, 522, 524} and attempt < 2:
                        time.sleep((1, 3)[attempt])
                        continue
                    raise RuntimeError(f"HTTP {exc.code}: {text}") from None
                except RemoteDisconnected:
                    if attempt < 2:
                        time.sleep((1, 3)[attempt])
                        continue
                    raise
        finally:
            self.last_seconds = time.perf_counter() - start
