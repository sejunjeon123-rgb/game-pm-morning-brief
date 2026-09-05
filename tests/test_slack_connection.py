import unittest
from unittest.mock import Mock, patch

from shared.slack_client import SlackDeliveryError, format_connection_test, post_webhook


class SlackConnectionTests(unittest.TestCase):
    def test_test_message_is_fixed_and_contains_no_other_service(self):
        payload = format_connection_test()
        text = str(payload)
        self.assertIn("연결 테스트", text)
        self.assertIn("게임 수집·OpenAI 호출·Notion 생성 없이", text)
        self.assertNotIn("webhook_url", text.lower())

    def test_webhook_accepts_only_slack_https_host(self):
        with self.assertRaises(SlackDeliveryError):
            post_webhook("https://example.com/private", format_connection_test())

    def test_success_requires_slack_ok_response(self):
        response = Mock(status=200)
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b"ok"
        with patch("shared.slack_client.urlopen", return_value=response):
            post_webhook("https://hooks.slack.com/services/test", format_connection_test())
