import unittest

from shared.notion_client import NotionDeliveryError, format_connection_test_page


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
