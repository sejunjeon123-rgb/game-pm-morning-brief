"""Unit tests for fail-closed OpenAI response parsing."""

from __future__ import annotations

import unittest

from shared.openai_client import OpenAIClientError, OpenAIResponsesClient


class OpenAIResponsesClientTests(unittest.TestCase):
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
