import json
import unittest
from unittest.mock import Mock, patch

from shared.notion_client import NotionDeliveryError, create_page, format_connection_test_page


class NotionConnectionTests(unittest.TestCase):
    def test_minimal_test_page_is_child_of_configured_parent(self):
        parent = "3d2048e74f21808ab587f57b29b006d2"
        payload = format_connection_test_page(parent, "2026-09-05T14:00:00+09:00")
        self.assertEqual(payload["parent"], {"type": "page_id", "page_id": parent})
        self.assertIn("연결 테스트 | 2026-09-05", str(payload))
        self.assertIn("OpenAI 호출 및 Slack 발송 없음", str(payload))
        self.assertNotIn("token", str(payload).lower())

    def test_invalid_parent_is_rejected_before_request(self):
        with self.assertRaises(NotionDeliveryError):
            format_connection_test_page("not-a-page", "2026-09-05T14:00:00+09:00")

    def test_create_page_builds_stable_url_when_response_omits_it(self):
        page_id = "3d2048e7-4f21-808a-b587-f57b29b006d2"
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps({"object": "page", "id": page_id}).encode()
        with patch("shared.notion_client.urlopen", return_value=response):
            result = create_page("private", {"object": "test"}, retries=0)
        self.assertEqual(result["page_id"], page_id)
        self.assertEqual(result["page_url"], "https://www.notion.so/3d2048e74f21808ab587f57b29b006d2")

    def test_create_page_rejects_response_without_page_id(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"object":"page","request_id":"safe"}'
        with patch("shared.notion_client.urlopen", return_value=response), self.assertRaises(NotionDeliveryError) as error:
            create_page("private", {"object": "test"}, retries=0)
        self.assertIn("fields=object,request_id", str(error.exception))
        self.assertNotIn("safe", str(error.exception))
