from __future__ import annotations

import unittest
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from market_signal.listing_parser import parse_listing
from market_signal.analyzer import analyze_notices
from market_signal.runner import analyze_collection_file
from market_signal.models import CollectedNotice
from market_signal.normalize import content_hash, extract_text, extract_text_from_class
from market_signal.official_board_adapters import parse_naver_cafe_articles, parse_naver_lounge_feeds, parse_netmarble_articles, parse_odin_homepage, parse_plaync_article, parse_stove_article
from market_signal.youtube_collector import _parse_feed
from shared.time_utils import KST


FIXTURES = Path(__file__).parent / "fixtures"


class MarketSignalTests(unittest.TestCase):
    def test_mabinogi_listing_parser(self) -> None:
        html = (FIXTURES / "mabinogi_notice_list.html").read_text(encoding="utf-8")
        items = parse_listing("mabinogi-mobile", "https://mabinogimobile.nexon.com/News/Notice", html)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].title, "8/27(목) 신규 패키지 안내")
        self.assertEqual(items[0].published_at, datetime(2026, 8, 27, tzinfo=KST))

    def test_black_desert_listing_parser(self) -> None:
        html = (FIXTURES / "black_desert_notice_list.html").read_text(encoding="utf-8")
        items = parse_listing("black-desert-mobile", "https://forum.blackdesertm.com/Board?boardNo=6", html)
        self.assertEqual(len(items), 1)
        self.assertIn("contentNo=660799", items[0].url)

    def test_youtube_feed_and_publisher_filter(self) -> None:
        xml = (FIXTURES / "youtube_feed.xml").read_text(encoding="utf-8")
        now = datetime(2026, 8, 30, tzinfo=KST)
        items = _parse_feed("trickcal-revive", xml, now, ("트릭컬", "Trickcal"))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source_type, "OFFICIAL_YOUTUBE")
        self.assertEqual(items[0].title, "트릭컬 리바이브 신규 이벤트 안내")

    def test_detail_normalization_ignores_script_and_header_when_scoped(self) -> None:
        html = (FIXTURES / "mabinogi_notice_detail.html").read_text(encoding="utf-8")
        text = extract_text(html)
        self.assertIn("신규 패키지 판매 기간", text)
        self.assertNotIn("dynamicTrackingId", text)
        self.assertNotIn("공통 메뉴", text)

    def test_class_scoped_extraction_excludes_dynamic_forum_fields(self) -> None:
        html = '<div class="view-count">101</div><div class="contents_area ck-content"><p>공식 본문<br><img src="x"></p></div><div class="replyItem">동적 댓글</div>'
        text = extract_text_from_class(html, "contents_area")
        self.assertEqual(text, "공식 본문")

    def test_change_type(self) -> None:
        now = datetime(2026, 8, 27, tzinfo=KST)
        new = CollectedNotice("mabinogi-mobile", "https://example.com/1", "title", now, now, "body", content_hash("body"))
        same = CollectedNotice("mabinogi-mobile", "https://example.com/1", "title", now, now, "body", content_hash("body"), content_hash("body"))
        changed = CollectedNotice("mabinogi-mobile", "https://example.com/1", "title", now, now, "body2", content_hash("body2"), content_hash("body"))
        self.assertEqual(new.change_type, "NEW")
        self.assertEqual(same.change_type, "UNCHANGED")
        self.assertEqual(changed.change_type, "MODIFIED")

    def test_netmarble_forum_adapter_parses_official_article(self) -> None:
        payload = {"articleList": [{
            "id": 1986, "menuSeq": 20, "title": "공식 공지",
            "content": "<p>점검 및 업데이트 안내</p>",
            "regDate": 1787961609789, "delFlag": 0,
        }]}
        items = parse_netmarble_articles(payload, menu_id=20)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].game_id, "seven-knights-rebirth")
        self.assertEqual(items[0].normalized_text, "점검 및 업데이트 안내")
        self.assertIn("/view/20/1986", items[0].url)

    def test_naver_cafe_adapter_parses_official_article(self) -> None:
        payload = {"result": {"articleList": [{"type": "ARTICLE", "item": {
            "articleId": 208417, "menuId": 66, "subject": "문제 현상 안내(수정)",
            "summary": "확인된 문제 현상과 수정 내용을 안내합니다.",
            "writeDateTimestamp": 1787816896513, "blindArticle": False,
        }}]}}
        items = parse_naver_cafe_articles(payload, menu_id=66)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].game_id, "trickcal-revive")
        self.assertEqual(items[0].source_type, "OFFICIAL_COMMUNITY")
        self.assertIn("/articles/208417", items[0].url)

    def test_odin_homepage_adapter_uses_dated_news_only(self) -> None:
        html = '''<a id="a_main_news_article" href="https://odin.kakaogames.com/odin/">8/26(수) 업데이트 상세 내역 안내</a>
        <a id="a_main_news_article" href="https://odin.kakaogames.com/odin/">진행 중인 이벤트 모아보기</a>'''
        items = parse_odin_homepage(html, reference=datetime(2026, 8, 30, tzinfo=KST))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].published_at, datetime(2026, 8, 26, tzinfo=KST))
        self.assertEqual(items[0].source_type, "OFFICIAL_HOMEPAGE")
        self.assertEqual(items[0].url, "https://odin.kakaogames.com/odin/")

    def test_plaync_adapter_parses_full_official_article(self) -> None:
        payload = {"article": {
            "contentMeta": {
                "id": "6a916a306b722c561dc6a2ca",
                "title": "[안내] 공식 상품 안내",
                "timestamps": {"publishedAt": "2026-08-28T11:00:00.921Z"},
            },
            "content": {"content": "<div><p>상품 판매 기간과 구성을 안내합니다.</p></div>"},
        }}
        item = parse_plaync_article(payload)
        self.assertEqual(item.game_id, "lineage-m")
        self.assertEqual(item.normalized_text, "상품 판매 기간과 구성을 안내합니다.")
        self.assertEqual(item.published_at.tzinfo, KST)
        self.assertIn("articleId=6a916", item.url)

    def test_nikke_lounge_adapter_extracts_editor_text(self) -> None:
        body = {"document": {"components": [{"value": [{"nodes": [
            {"value": "안녕하세요. ", "@ctype": "textNode"},
            {"value": "업데이트 내용을 안내합니다.", "@ctype": "textNode"},
        ]}]}]}}
        payload = {"content": {"feeds": [{"feed": {
            "feedId": 8094241, "title": "업데이트 안내",
            "createdDate": "20260823182318", "contents": json.dumps(body, ensure_ascii=False),
        }}]}}
        items = parse_naver_lounge_feeds(payload)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].normalized_text, "안녕하세요. 업데이트 내용을 안내합니다.")
        self.assertEqual(items[0].source_type, "OFFICIAL_COMMUNITY")
        self.assertIn("/board/detail/8094241", items[0].url)

    def test_stove_adapter_parses_full_official_article(self) -> None:
        payload = {"code": 0, "value": {
            "article_id": "14452785", "title": "8/28(금) 현재 확인된 문제점 안내",
            "content": "<p>현재 확인된 문제점과 조치 상황을 안내합니다.</p>",
            "create_datetime": 1787924305133,
        }}
        item = parse_stove_article(payload)
        self.assertEqual(item.game_id, "epic-seven")
        self.assertEqual(item.normalized_text, "현재 확인된 문제점과 조치 상황을 안내합니다.")
        self.assertEqual(item.source_type, "OFFICIAL_COMMUNITY")
        self.assertIn("/view/14452785", item.url)

    def test_structured_analysis_builds_valid_routed_signal(self) -> None:
        class FakeClient:
            def structured(self, **_: object) -> dict[str, object]:
                return {
                    "event_key": "new-package-2026-08-27",
                    "title": "신규 패키지 안내",
                    "summary": "공식 아이템샵에 신규 패키지가 추가됐다.",
                    "category": "BM",
                    "severity": "HIGH",
                    "bm_item_types": ["GROWTH", "CURRENCY"],
                    "pm_terms": ["NPU", "PUR", "ARPPU"],
                    "pm_rationale": "신규 상품의 결제 진입과 객단가 관련 내부 지표 확인이 필요하다.",
                    "severity_reason": "한정 판매 상품 구조로 Player Live 반응 확인이 필요하다.",
                }

        now = datetime(2026, 8, 27, tzinfo=KST)
        notice = CollectedNotice(
            "mabinogi-mobile", "https://example.com/notice/1", "신규 패키지 안내",
            now, now, "공식 패키지 구성 안내", content_hash("공식 패키지 구성 안내"),
        )
        signal = analyze_notices(FakeClient(), (notice,))[0]  # type: ignore[arg-type]
        self.assertEqual(signal.category.value, "BM")
        self.assertTrue(signal.routing.deep_dive_required)
        self.assertEqual(signal.routing.target.value, "player-live-watch")

    def test_saved_collection_analysis_fails_closed_without_openai_config(self) -> None:
        now = "2026-08-27T08:00:00+09:00"
        payload = {"notices": [{
            "game_id": "mabinogi-mobile", "url": "https://example.com/notice/1",
            "title": "공지", "published_at": now, "collected_at": now,
            "normalized_text": "공식 공지 본문", "content_hash": content_hash("공식 공지 본문"),
        }], "videos": []}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "collection.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            old_key, old_model = os.environ.pop("OPENAI_API_KEY", None), os.environ.pop("OPENAI_MODEL", None)
            try:
                result = analyze_collection_file(path)
            finally:
                if old_key is not None:
                    os.environ["OPENAI_API_KEY"] = old_key
                if old_model is not None:
                    os.environ["OPENAI_MODEL"] = old_model
        self.assertEqual(result["analysis_status"], "blocked_missing_openai_configuration")
        self.assertEqual(result["input_count"], 1)


if __name__ == "__main__":
    unittest.main()
