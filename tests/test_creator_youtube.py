import json
import unittest
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch

from app.config import load_project_config
from app.daily import validate_summary, _decision
from player_live_watch.creator_youtube import collect_creator_youtube, creator_sources
from shared.http_client import HttpResponse, HttpClientError
from shared.time_utils import KST


class CreatorTests(unittest.TestCase):
    def setUp(self):
        self.config = load_project_config(Path(__file__).resolve().parents[1])
        self.now = datetime(2026, 9, 4, 12, tzinfo=KST)

    def test_twelve_channels_and_odin_empty(self):
        self.assertEqual(sum(len(creator_sources(self.config, g)) for g in self.config.game_ids), 12)
        self.assertEqual(creator_sources(self.config, "odin-valhalla-rising"), [])

    def test_feed_is_creator_not_official_and_one_per_channel(self):
        http = Mock()
        def get(url):
            channel = url.split("channel_id=")[1]
            xml = f'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:yt="http://www.youtube.com/xml/schemas/2015">
              <yt:channelId>{channel}</yt:channelId>
              <entry><yt:videoId>abcdefghijk</yt:videoId><title>마비노기 모바일 업데이트 의견</title>
              <published>2026-09-03T12:00:00Z</published><link href="https://www.youtube.com/watch?v=abcdefghijk"/></entry></feed>'''
            return HttpResponse(url, 200, {}, xml.encode())
        http.get.side_effect = get
        result = collect_creator_youtube(self.config, ("mabinogi-mobile",), client=http, now=self.now)
        self.assertEqual(len(result["evidence"]), 2)
        for item in result["evidence"]:
            self.assertEqual(item["source_type"], "PUBLIC_CREATOR_YOUTUBE")
            self.assertEqual(item["classification"], "CREATOR_ANALYSIS")
            self.assertEqual(item["caption_status"], "NOT_COLLECTED")

    def test_failure_is_bounded_and_does_not_block_other_sources(self):
        http = Mock()
        http.get.side_effect = HttpClientError("unavailable")
        with patch("player_live_watch.creator_youtube.collect_channel_fallback", return_value=()) as fallback:
            report = collect_creator_youtube(self.config, ("mabinogi-mobile",), client=http, now=self.now)
        self.assertEqual(http.get.call_count, 2)
        self.assertEqual(fallback.call_count, 2)
        self.assertEqual(fallback.call_args.kwargs["max_videos"], 1)
        self.assertEqual(report["evidence"], [])

    def test_creator_only_report_and_fact_boundary(self):
        doc = {"evidence_id": "creator1", "classification": "CREATOR_ANALYSIS",
               "source_type": "PUBLIC_CREATOR_YOUTUBE", "url": "https://www.youtube.com/watch?v=abcdefghijk",
               "published_at": self.now, "collected_at": self.now, "content_hash": "a" * 64}
        sentence = {"text": "제작자는 업데이트에 대한 의견을 제시했습니다.", "evidence_ids": ["creator1"]}
        raw = {"title": "업데이트에 대한 제작자 견해", "category": "UPDATE", "bm_types": [],
               "facts": [], "claims": [], "interpretation": [sentence], "unknowns": [], "conflicts": []}
        item = validate_summary({"items": [raw]}, [doc])[0]
        decision = _decision("mabinogi-mobile", item, self.now, "마비노기 모바일")
        self.assertTrue(decision.executive_summary.startswith("제작자 견해:"))
        self.assertTrue(item["unknowns"])
        raw["facts"] = [sentence]
        with self.assertRaises(ValueError):
            validate_summary({"items": [raw]}, [doc])
