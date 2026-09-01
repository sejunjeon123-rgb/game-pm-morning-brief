"""Unit tests for fail-closed OpenAI response parsing."""

from __future__ import annotations

import unittest

from shared.openai_client import OpenAIClientError, OpenAIResponsesClient


class OpenAIResponsesClientTests(unittest.TestCase):
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
