"""Minimal standard-library client for OpenAI Responses structured outputs."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class OpenAIClientError(RuntimeError):
    pass


class OpenAIResponsesClient:
    endpoint = "https://api.openai.com/v1/responses"

    def __init__(self, api_key: str, model: str, *, timeout: float = 90.0) -> None:
        if not api_key or not model:
            raise ValueError("api_key and model are required")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def structured(self, *, instructions: str, input_text: str, name: str, schema: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "instructions": instructions,
            "input": input_text,
            "store": False,
            "text": {"format": {"type": "json_schema", "name": name, "strict": True, "schema": schema}},
        }
        request = Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            # Keep errors safe for public CI logs. The response body can contain
            # request-derived details and is intentionally not echoed here.
            raise OpenAIClientError(f"OpenAI API HTTP {exc.code}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise OpenAIClientError("OpenAI API request failed") from exc
        status = result.get("status")
        if status != "completed":
            raise OpenAIClientError(f"OpenAI response was not completed (status={status or 'unknown'})")
        output_text = result.get("output_text") or self._find_output_text(result)
        if not output_text:
            raise OpenAIClientError("OpenAI response did not contain output text")
        try:
            value = json.loads(output_text)
        except json.JSONDecodeError as exc:
            raise OpenAIClientError("OpenAI structured output was not valid JSON") from exc
        if not isinstance(value, dict):
            raise OpenAIClientError("OpenAI structured output must be a JSON object")
        return value

    @staticmethod
    def _find_output_text(result: dict[str, Any]) -> str:
        for item in result.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "refusal":
                    raise OpenAIClientError("OpenAI response was refused")
                if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                    return content["text"]
        return ""
