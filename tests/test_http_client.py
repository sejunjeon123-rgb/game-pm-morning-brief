import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError
from shared.http_client import HttpClient, HttpClientError


class HttpClientTests(unittest.TestCase):
    def test_transient_failure_retries_once_and_recovers(self):
        response = MagicMock()
        response.__enter__.return_value.status = 200
        response.__enter__.return_value.headers = {}
        response.__enter__.return_value.read.return_value = b"ok"
        with patch("shared.http_client.urlopen", side_effect=[URLError(TimeoutError()), response]) as request, patch("shared.http_client.time.sleep"):
            result = HttpClient(timeout=20, retries=1).get("https://example.com")
        self.assertEqual(result.body, b"ok")
        self.assertEqual(request.call_count, 2)

    def test_403_is_not_retried_and_secrets_not_logged(self):
        error = HTTPError("https://example.com?secret=abc", 403, "secret", {}, None)
        with patch("shared.http_client.urlopen", side_effect=error) as request:
            with self.assertRaises(HttpClientError) as caught:
                HttpClient(retries=1).get("https://example.com?secret=abc")
        self.assertEqual(caught.exception.code, "HTTP_403")
        self.assertNotIn("secret", str(caught.exception))
        request.assert_called_once()
