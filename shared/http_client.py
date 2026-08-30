"""Small standard-library HTTP client with bounded retries and safe defaults."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_USER_AGENT = "game-pm-morning-brief/1.0 (+public GitHub portfolio)"


class HttpClientError(RuntimeError):
    """Raised when a request cannot be completed within the retry policy."""


@dataclass(frozen=True, slots=True)
class HttpResponse:
    url: str
    status: int
    headers: Mapping[str, str]
    body: bytes

    def text(self, encoding: str | None = None) -> str:
        charset = encoding or _charset_from_content_type(self.headers.get("Content-Type", ""))
        return self.body.decode(charset or "utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.text())


def _charset_from_content_type(content_type: str) -> str | None:
    for part in content_type.split(";")[1:]:
        key, separator, value = part.strip().partition("=")
        if separator and key.lower() == "charset":
            return value.strip("\"' ")
    return None


class HttpClient:
    def __init__(self, *, timeout: float = 15.0, retries: int = 2, backoff: float = 0.5) -> None:
        if timeout <= 0 or retries < 0 or backoff < 0:
            raise ValueError("invalid HTTP retry settings")
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff

    def get(self, url: str, *, headers: Mapping[str, str] | None = None) -> HttpResponse:
        request_headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "*/*"}
        request_headers.update(headers or {})
        request = Request(url, headers=request_headers, method="GET")
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    return HttpResponse(response.geturl(), response.status, dict(response.headers.items()), response.read())
            except HTTPError as exc:
                last_error = exc
                if exc.code < 500 and exc.code != 429:
                    break
            except (URLError, TimeoutError) as exc:
                last_error = exc
            if attempt < self.retries:
                time.sleep(self.backoff * (2**attempt))
        raise HttpClientError(f"GET failed for {url}: {last_error}") from last_error

    def get_json(self, url: str, *, headers: Mapping[str, str] | None = None) -> Any:
        return self.get(url, headers=headers).json()
