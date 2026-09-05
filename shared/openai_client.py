"""Minimal standard-library client for OpenAI Responses structured outputs."""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from shared.http_client import transport_error_code


class OpenAIClientError(RuntimeError):
    def __init__(self, message: str, *, code: str = "API_ERROR") -> None:
        super().__init__(message)
        self.code = code


class OpenAIResponsesClient:
    endpoint = "https://api.openai.com/v1/responses"

    def __init__(self, api_key: str, model: str, *, timeout: float = 90.0, retries: int = 2, backoff: float = 1.0, max_output_tokens: int | None = None, reasoning_effort: str | None = None) -> None:
        if not api_key or not model:
            raise ValueError("api_key and model are required")
        if timeout <= 0 or retries < 0 or backoff < 0:
            raise ValueError("invalid OpenAI request settings")
        if reasoning_effort not in {None, "minimal", "low", "medium", "high"}:
            raise ValueError("invalid OpenAI reasoning effort")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.max_output_tokens = max_output_tokens
        self.reasoning_effort = reasoning_effort
        self.usage_records: list[dict[str, int]] = []

    def structured(self, *, instructions: str, input_text: str, name: str, schema: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "instructions": instructions,
            "input": input_text,
            "store": False,
            "text": {"format": {"type": "json_schema", "name": name, "strict": True, "schema": schema}},
        }
        if self.max_output_tokens is not None:
            payload["max_output_tokens"] = self.max_output_tokens
        if self.reasoning_effort is not None:
            payload["reasoning"] = {"effort": self.reasoning_effort}
        request = Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        result: dict[str, Any] | None = None
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            retry_after: str | None = None
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    result = json.loads(response.read().decode("utf-8"))
                break
            except HTTPError as exc:
                # Keep errors safe for public CI logs. The response body can contain
                # request-derived details and is intentionally not echoed here.
                last_error = exc
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                if exc.code != 429 and exc.code < 500:
                    raise OpenAIClientError(f"OpenAI API HTTP {exc.code}", code=f"HTTP_{exc.code}") from exc
            except (URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
            if attempt < self.retries:
                time.sleep(self._retry_delay(retry_after, attempt))
        if result is None:
            if isinstance(last_error, HTTPError):
                raise OpenAIClientError(f"OpenAI API HTTP {last_error.code} after bounded retries", code=f"HTTP_{last_error.code}") from last_error
            code = "INVALID_JSON" if isinstance(last_error, json.JSONDecodeError) else transport_error_code(last_error)
            raise OpenAIClientError("OpenAI API request failed after bounded retries", code=code) from last_error
        if not isinstance(result, dict):
            raise OpenAIClientError("Invalid response envelope", code="INVALID_JSON")
        usage = result.get("usage") or {}
        self.usage_records.append({key: int(usage.get(key, 0)) for key in ("input_tokens", "output_tokens", "total_tokens")})
        self.usage_records[-1]["reasoning_tokens"] = int((usage.get("output_tokens_details") or {}).get("reasoning_tokens", 0))
        status = result.get("status")
        if status != "completed":
            reason = (result.get("incomplete_details") or {}).get("reason")
            code = "OUTPUT_TOKEN_LIMIT" if status == "incomplete" and reason == "max_output_tokens" else "INCOMPLETE_RESPONSE"
            raise OpenAIClientError("OpenAI response was not completed", code=code)
        output_text = result.get("output_text") or self._find_output_text(result)
        if not output_text:
            raise OpenAIClientError("OpenAI response did not contain output text", code="EMPTY_OUTPUT")
        try:
            value = json.loads(output_text)
        except json.JSONDecodeError as exc:
            raise OpenAIClientError("OpenAI structured output was not valid JSON", code="INVALID_JSON") from exc
        if not isinstance(value, dict):
            raise OpenAIClientError("OpenAI structured output must be a JSON object", code="INVALID_JSON")
        return value

    def _retry_delay(self, retry_after: str | None, attempt: int) -> float:
        if retry_after:
            try:
                return min(max(float(retry_after), 0.0), 20.0)
            except ValueError:
                pass
        return min(self.backoff * (2**attempt), 20.0)

    @staticmethod
    def _find_output_text(result: dict[str, Any]) -> str:
        for item in result.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "refusal":
                    raise OpenAIClientError("OpenAI response was refused", code="REFUSAL")
                if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                    return content["text"]
        return ""
