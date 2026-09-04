"""Unit tests for fail-closed OpenAI response parsing."""

from __future__ import annotations

import unittest
import json
from unittest.mock import patch, MagicMock

from shared.openai_client import OpenAIClientError, OpenAIResponsesClient


class OpenAIResponsesClientTests(unittest.TestCase):
    def test_output_cap_and_usage_are_recorded_without_real_api(self):
        client = OpenAIResponsesClient("test-key", "test-model", retries=0, max_output_tokens=2500)
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({
            "status": "completed", "output_text": '{"items": []}',
            "usage": {"input_tokens": 12, "output_tokens": 8, "total_tokens": 20},
        }).encode()
        with patch("shared.openai_client.urlopen", return_value=response) as request:
            client.structured(instructions="test", input_text="test", name="test", schema={})
        payload = json.loads(request.call_args.args[0].data)
        self.assertEqual(payload["max_output_tokens"], 2500)
        self.assertEqual(client.usage_records[0]["total_tokens"], 20)
        request.assert_called_once()

    def test_retry_delay_respects_numeric_retry_after_and_cap(self) -> None:
        client = OpenAIResponsesClient("test-key", "test-model", backoff=2)
        self.assertEqual(client._retry_delay("3", 0), 3)
        self.assertEqual(client._retry_delay("999", 0), 20)
        self.assertEqual(client._retry_delay(None, 2), 8)

    def test_finds_structured_output_text(self) -> None:
        result = {
            "status": "completed",
            "output": [{"content": [{"type": "output_text", "text": '{"ok": true}'}]}],
        }
        self.assertEqual(OpenAIResponsesClient._find_output_text(result), '{"ok": true}')

    def test_refusal_fails_closed(self) -> None:
        result = {
            "status": "completed",
            "output": [{"content": [{"type": "refusal", "refusal": "cannot comply"}]}],
        }
        with self.assertRaises(OpenAIClientError):
            OpenAIResponsesClient._find_output_text(result)


if __name__ == "__main__":
    unittest.main()
