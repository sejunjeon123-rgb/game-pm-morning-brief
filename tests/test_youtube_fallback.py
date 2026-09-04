import json
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime
from unittest.mock import Mock, patch

from market_signal.youtube_fallback import parse_watch, collect_channel_fallback
from market_signal.diagnostics import response_metadata
from market_signal.youtube_collector import collect_official_youtube
from shared.http_client import HttpResponse, HttpClientError
from shared.state_store import StateStore
from shared.time_utils import KST


class FallbackTests(unittest.TestCase):
    now = datetime(2026, 9, 4, 12, tzinfo=KST)

    def watch(self, date="2026-09-03T10:00:00+09:00", channel="official", **extra):
        data = {"videoDetails": {"channelId": channel, "videoId": "abcdefghijk",
                                 "title": "공식 업데이트", "shortDescription": "공식 설명", **extra},
                "playabilityStatus": {"status": "OK"},
                "microformat": {"playerMicroformatRenderer": {"publishDate": date}}}
        return "var ytInitialPlayerResponse = " + json.dumps(data)

    def test_recent_official_metadata(self):
        item = parse_watch(self.watch(), "game", "official", "abcdefghijk", self.now)
        self.assertEqual(item.source_type, "OFFICIAL_YOUTUBE")
        self.assertIn("공식 설명", item.normalized_text)

    def test_reject_unknown_dates_and_identity(self):
        for date in ("", "2026-09-03", "2 days ago"):
            with self.assertRaises(ValueError):
                parse_watch(self.watch(date), "game", "official", "abcdefghijk", self.now)
        with self.assertRaises(ValueError):
            parse_watch(self.watch(channel="creator"), "game", "official", "abcdefghijk", self.now)

    def test_old_future_live_and_filter_are_excluded(self):
        for html in (self.watch("2026-08-01T00:00:00Z"), self.watch("2026-09-05T00:00:00Z"),
                     self.watch(isLiveContent=True)):
            self.assertIsNone(parse_watch(html, "game", "official", "abcdefghijk", self.now))
        self.assertIsNone(parse_watch(self.watch(), "game", "official", "abcdefghijk", self.now, ("other game",)))

    def test_bounded_fallback_and_dedup(self):
        source = {"game_id": "game", "youtube": "https://www.youtube.com/@official", "youtube_channel_id": "official"}
        metadata = {"channelMetadataRenderer": {"externalId": "official"}}
        home = {"metadata": metadata, "contents": {"tabRenderer": {"endpoint": {
            "browseEndpoint": {"browseId": "official"},
            "commandMetadata": {"webCommandMetadata": {"url": "/@official/videos"}}}}}}
        listing = {"metadata": metadata, "contents": [{"videoRenderer": {"videoId": v}} for v in
                   ("abcdefghijk", "abcdefghijk", "bcdefghijkl", "cdefghijklm", "defghijklmn")]}
        http = Mock()
        def get(url):
            html = ("var ytInitialData = " + json.dumps(home if url.endswith("@official") else listing)
                    if "watch?" not in url else self.watch())
            return HttpResponse(url, 200, {}, html.encode())
        http.get.side_effect = get
        self.assertEqual(len(collect_channel_fallback(http, source, self.now)), 1)
        self.assertEqual(http.get.call_count, 5)

    def test_modern_selected_video_tab_avoids_duplicate_request(self):
        source = {"game_id": "game", "youtube": "https://www.youtube.com/@official/videos",
                  "youtube_channel_id": "official"}
        tab = {"selected": True, "endpoint": {
            "browseEndpoint": {"browseId": "official"},
            "commandMetadata": {"webCommandMetadata": {"url": "/@official/videos"}}},
            "content": [{"lockupViewModel": {"contentId": "abcdefghijk",
                         "contentType": "LOCKUP_CONTENT_TYPE_VIDEO"}},
                        {"watchEndpoint": {"videoId": "unrelated01"}},
                        {"lockupViewModel": {"contentId": "playlist001",
                         "contentType": "LOCKUP_CONTENT_TYPE_PLAYLIST"}}]}
        listing = {"metadata": {"channelMetadataRenderer": {"externalId": "official"}},
                   "contents": {"tabRenderer": tab}}
        http = Mock()
        http.get.side_effect = [HttpResponse(source["youtube"], 200, {},
            ("var ytInitialData = " + json.dumps(listing)).encode()),
            HttpResponse("https://www.youtube.com/watch?v=abcdefghijk", 200, {}, self.watch().encode())]
        stats = {}
        self.assertEqual(len(collect_channel_fallback(http, source, self.now, diagnostics=stats)), 1)
        self.assertEqual(http.get.call_count, 2)
        self.assertEqual(stats, {"candidates": 1, "accepted": 1})

    def test_old_video_is_not_reported_as_access_failure(self):
        stats = {}
        self.assertIsNone(parse_watch(self.watch("2026-08-01T00:00:00Z"), "game",
                                     "official", "abcdefghijk", self.now, diagnostics=stats))
        self.assertEqual(stats, {"outside_window": 1})

    def test_request_budget_cannot_be_expanded(self):
        with self.assertRaises(ValueError):
            collect_channel_fallback(Mock(), {}, self.now, max_videos=4)

    def test_diagnostics_do_not_expose_server_text_or_redirect(self):
        response = HttpResponse("https://other.example/?token=secret", 200, {}, b"<html><title>secret</title></html>")
        result = response_metadata(response, "https://example.com")
        self.assertNotIn("secret", json.dumps(result))
        self.assertFalse(result["same_host"])
        self.assertEqual(result["final_path"], "REDACTED")

    def test_diagnostic_same_host_route_excludes_query(self):
        response = HttpResponse("https://example.com/Error/Region?token=secret", 200, {}, b"<html></html>")
        result = response_metadata(response, "https://example.com/News/Notice")
        self.assertEqual(result["final_path"], "/Error/Region")
        self.assertNotIn("secret", json.dumps(result))

    def test_rss_failure_keeps_gap_and_fallback_success(self):
        config = SimpleNamespace(sources=[{"game_id": "game", "youtube_channel_id": "official"}])
        http = Mock()
        http.get.side_effect = HttpClientError("unavailable", code="HTTP_404")
        item = parse_watch(self.watch(), "game", "official", "abcdefghijk", self.now)
        with tempfile.TemporaryDirectory() as directory, \
             patch("market_signal.youtube_collector.collect_channel_fallback", return_value=(item,)) as fallback:
            result = collect_official_youtube(config, StateStore(Path(directory)), ("game",), client=http)
        self.assertEqual(len(result["videos"]), 1)
        self.assertEqual(result["coverage_gaps"][0]["code"], "HTTP_404")
        fallback.assert_called_once()

    def test_valid_empty_rss_does_not_trigger_extra_requests(self):
        config = SimpleNamespace(sources=[{"game_id": "game", "youtube_channel_id": "official"}])
        http = Mock()
        http.get.return_value = HttpResponse("https://www.youtube.com/", 200, {}, b'<feed xmlns="http://www.w3.org/2005/Atom"/>')
        with tempfile.TemporaryDirectory() as directory, \
             patch("market_signal.youtube_collector.collect_channel_fallback") as fallback:
            result = collect_official_youtube(config, StateStore(Path(directory)), ("game",), client=http)
        self.assertEqual(result["videos"], [])
        fallback.assert_not_called()
