from __future__ import annotations

import unittest
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from market_signal.listing_parser import parse_listing
from market_signal.analyzer import analyze_notices, analyze_notices_with_report
from app.config import ProjectConfig
from market_signal.collector import _collect_html_documents, collect_official_notices
from market_signal.runner import analyze_collection_file
from market_signal.models import CollectedNotice, NoticeCandidate
from market_signal.normalize import content_hash, extract_text, extract_text_from_attribute, extract_text_from_class
from market_signal.official_board_adapters import parse_naver_cafe_articles, parse_naver_lounge_feeds, parse_netmarble_articles, parse_odin_homepage, parse_plaync_article, parse_stove_article
from market_signal.youtube_collector import _parse_feed
from shared.state_store import StateStore
from shared.schemas import PMMetricContext
from shared.time_utils import KST
from shared.http_client import HttpClientError, HttpResponse
from shared.pm_metrics import sanitize_pm_metric_context


FIXTURES = Path(__file__).parent / "fixtures"


class MarketSignalTests(unittest.TestCase):
    def test_mabinogi_listing_parser(self) -> None:
        html = (FIXTURES / "mabinogi_notice_list.html").read_text(encoding="utf-8")
        items = parse_listing("mabinogi-mobile", "https://mabinogimobile.nexon.com/News/Notice", html)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].title, "8/27(목) 신규 패키지 안내")
        self.assertEqual(items[0].published_at, datetime(2026, 8, 27, tzinfo=KST))

    def test_mabinogi_verified_thread_markup_parser(self) -> None:
        html = '''<ul><li class="item" data-threadid="3532703">
        <a href="/News/Notice/3532703"><span>신규 패키지 안내</span></a>
        <div><span>마비노기모바일</span><span>0</span><span>2026.08.26</span></div>
        </li></ul>'''
        items = parse_listing("mabinogi-mobile", "https://mabinogimobile.nexon.com/News/Notice", html)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].url, "https://mabinogimobile.nexon.com/News/Notice/3532703")
        self.assertEqual(items[0].published_at, datetime(2026, 8, 26, tzinfo=KST))

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

    def test_attribute_scoped_extraction_uses_visible_nexon_body(self) -> None:
        html = '<div data-blockmsg>차단 문구</div><div data-blockcontent><p>공식 본문</p></div><div>댓글</div>'
        self.assertEqual(extract_text_from_attribute(html, "data-blockcontent"), "공식 본문")

    def test_mabinogi_detail_failure_does_not_discard_successful_notices(self) -> None:
        class PartialClient:
            def get(self, url: str) -> HttpResponse:
                if url.endswith("/2"):
                    raise HttpClientError("simulated detail failure")
                return HttpResponse(url, 200, {"Content-Type": "text/html; charset=utf-8"}, b"<div data-blockcontent>official body</div>")

        published = datetime(2026, 8, 27, tzinfo=KST)
        candidates = (
            NoticeCandidate("mabinogi-mobile", "https://mabinogimobile.nexon.com/News/Notice/1", "공지 1", published),
            NoticeCandidate("mabinogi-mobile", "https://mabinogimobile.nexon.com/News/Notice/2", "공지 2", published),
        )
        documents, gaps = _collect_html_documents("mabinogi-mobile", candidates, PartialClient())  # type: ignore[arg-type]
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].url, candidates[0].url)
        self.assertEqual(len(gaps), 1)
        self.assertIn(candidates[1].url, gaps[0]["reason"])

    def test_mabinogi_listing_uses_public_query_fallback_when_base_is_empty(self) -> None:
        listing = (FIXTURES / "mabinogi_notice_list.html").read_bytes()

        class FallbackClient:
            def get(self, url: str, *, headers: object = None) -> HttpResponse:
                if "?directionType=" in url:
                    return HttpResponse(url, 200, {"Content-Type": "text/html; charset=utf-8"}, listing)
                if url.rstrip("/").endswith("/News/Notice"):
                    return HttpResponse(url, 200, {"Content-Type": "text/html; charset=utf-8"}, b"<html><body></body></html>")
                body = "<div data-blockcontent>공식 공지 본문입니다.</div>".encode("utf-8")
                return HttpResponse(url, 200, {"Content-Type": "text/html; charset=utf-8"}, body)

        config = ProjectConfig(
            root=Path("."), runtime={}, games=(),
            sources=({
                "game_id": "mabinogi-mobile",
                "homepage": "https://mabinogimobile.nexon.com/Main",
                "notices": "https://mabinogimobile.nexon.com/News/Notice",
            },),
            source_policy={},
        )
        with tempfile.TemporaryDirectory() as directory:
            report = collect_official_notices(
                config, StateStore(Path(directory)), ("mabinogi-mobile",),
                client=FallbackClient(), max_details_per_game=2,  # type: ignore[arg-type]
                now=datetime(2026, 9, 2, 8, 0, tzinfo=KST),
            )
        self.assertEqual(len(report["notices"]), 1)
        self.assertEqual(report["notices"][0]["title"], "8/27(목) 신규 패키지 안내")
        self.assertEqual(report["coverage_gaps"], [])

    def test_pm_metric_semantics_reject_pickup_and_content_usage_aliases(self) -> None:
        terms, rationale = sanitize_pm_metric_context(
            ("PU", "CU", "Sales"),
            "픽업 캐릭터와 신규 콘텐츠가 매출에 미칠 영향은 내부 Sales 지표로 확인할 필요가 있다.",
        )
        self.assertEqual(terms, ("Sales",))
        self.assertTrue(rationale)

    def test_pm_metric_semantics_accept_canonical_verification_context(self) -> None:
        terms, rationale = sanitize_pm_metric_context(
            ("PU", "PUR", "ARPPU"),
            "신규 상품 출시 후 일간 결제 사용자 수, 결제율, 결제 사용자당 객단가를 내부 지표로 확인할 필요가 있다.",
        )
        self.assertEqual(terms, ("PU", "PUR", "ARPPU"))
        self.assertIn("확인", rationale)

    def test_pm_metric_context_rejects_unsupported_measured_direction(self) -> None:
        with self.assertRaisesRegex(ValueError, "without asserted KPI movement"):
            PMMetricContext(("DAU",), "공개 이벤트 이후 DAU가 증가했다고 확인했다.", True)

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
            model = "test-model"

            def structured(self, **kwargs: object) -> dict[str, object]:
                input_id = json.loads(str(kwargs["input_text"]))["documents"][0]["input_id"]
                return {
                    "events": [{
                        "event_key": "new-package-2026-08-27",
                        "input_ids": [input_id],
                        "title": "신규 패키지 안내",
                        "summary": "공식 아이템샵에 신규 패키지가 추가됐다.",
                        "category": "BM",
                        "severity": "HIGH",
                        "bm_item_types": ["GROWTH", "CURRENCY"],
                        "pm_terms": ["NPU", "PUR", "ARPPU"],
                        "pm_rationale": "신규 상품의 결제 진입과 객단가 관련 내부 지표 확인이 필요하다.",
                        "severity_reason": "한정 판매 상품 구조로 Player Live 반응 확인이 필요하다.",
                        "source_conflicts": [],
                    }],
                    "excluded_inputs": [],
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

    def test_batch_analysis_merges_multiple_evidence_and_accounts_for_every_input(self) -> None:
        class FakeClient:
            model = "test-model"
            calls = 0

            def structured(self, **kwargs: object) -> dict[str, object]:
                self.calls += 1
                documents = json.loads(str(kwargs["input_text"]))["documents"]
                return {
                    "events": [{
                        "event_key": "summer-update-2026-08-27",
                        "input_ids": [item["input_id"] for item in documents],
                        "title": "여름 업데이트",
                        "summary": "공식 공지와 영상이 같은 업데이트를 안내했다.",
                        "category": "UPDATE",
                        "severity": "MEDIUM",
                        "bm_item_types": [],
                        "pm_terms": ["Retention", "TS"],
                        "pm_rationale": "콘텐츠 이용 변화를 내부 지표로 확인할 필요가 있다.",
                        "severity_reason": "주요 콘텐츠 업데이트다.",
                        "source_conflicts": [],
                    }],
                    "excluded_inputs": [],
                }

        now = datetime(2026, 8, 27, tzinfo=KST)
        notices = (
            CollectedNotice("mabinogi-mobile", "https://example.com/notice/1", "여름 업데이트", now, now, "업데이트 상세", content_hash("업데이트 상세"), source_type="OFFICIAL_HOMEPAGE"),
            CollectedNotice("mabinogi-mobile", "https://youtube.com/watch?v=1", "여름 업데이트 영상", now, now, "업데이트 영상", content_hash("업데이트 영상"), source_type="OFFICIAL_YOUTUBE"),
        )
        client = FakeClient()
        outcome = analyze_notices_with_report(client, notices)  # type: ignore[arg-type]
        self.assertEqual(client.calls, 1)
        self.assertEqual(outcome.metrics["input_count"], 2)
        self.assertEqual(len(outcome.signals), 1)
        self.assertEqual(len(outcome.signals[0].evidence), 2)

    def test_batch_analysis_fails_closed_when_an_input_is_missing(self) -> None:
        class FakeClient:
            model = "test-model"

            def structured(self, **_: object) -> dict[str, object]:
                return {"events": [], "excluded_inputs": []}

        now = datetime(2026, 8, 27, tzinfo=KST)
        notice = CollectedNotice("mabinogi-mobile", "https://example.com/1", "공지", now, now, "본문", content_hash("본문"))
        with self.assertRaisesRegex(ValueError, "completeness gate failed"):
            analyze_notices_with_report(FakeClient(), (notice,))  # type: ignore[arg-type]

    def test_batch_analysis_retries_once_for_completeness_correction(self) -> None:
        class FakeClient:
            model = "test-model"

            def __init__(self) -> None:
                self.calls = 0

            def structured(self, **kwargs: object) -> dict[str, object]:
                self.calls += 1
                document = json.loads(str(kwargs["input_text"]))["documents"][0]
                if self.calls == 1:
                    return {"events": [], "excluded_inputs": []}
                return {
                    "events": [{
                        "event_key": "corrected-notice", "input_ids": [document["input_id"]],
                        "title": "공식 공지 안내", "summary": "누락된 공식 공지를 교정 응답에 포함했다.",
                        "category": "NOTICE", "severity": "LOW", "bm_item_types": [],
                        "pm_terms": [], "pm_rationale": "", "severity_reason": "일반적인 공식 안내다.",
                        "source_conflicts": [],
                    }],
                    "excluded_inputs": [],
                }

        now = datetime(2026, 8, 27, tzinfo=KST)
        notice = CollectedNotice("mabinogi-mobile", "https://example.com/1", "공지", now, now, "본문", content_hash("본문"))
        client = FakeClient()
        outcome = analyze_notices_with_report(client, (notice,))  # type: ignore[arg-type]
        self.assertEqual(client.calls, 2)
        self.assertEqual(outcome.metrics["validation_retry_count"], 1)
        self.assertEqual(outcome.metrics["api_call_count"], 2)

    def test_batch_analysis_fails_closed_on_english_generated_prose(self) -> None:
        class FakeClient:
            model = "test-model"

            def structured(self, **kwargs: object) -> dict[str, object]:
                document = json.loads(str(kwargs["input_text"]))["documents"][0]
                return {
                    "events": [{
                        "event_key": "english-output", "input_ids": [document["input_id"]],
                        "title": "English title", "summary": "English-only generated summary.",
                        "category": "NOTICE", "severity": "LOW", "bm_item_types": [],
                        "pm_terms": [], "pm_rationale": "", "severity_reason": "Routine notice.",
                        "source_conflicts": [],
                    }],
                    "excluded_inputs": [],
                }

        now = datetime(2026, 8, 27, tzinfo=KST)
        notice = CollectedNotice("mabinogi-mobile", "https://example.com/1", "공지", now, now, "본문", content_hash("본문"))
        with self.assertRaisesRegex(ValueError, "must be Korean prose"):
            analyze_notices_with_report(FakeClient(), (notice,))  # type: ignore[arg-type]

    def test_batch_analysis_normalizes_safe_event_key_separators(self) -> None:
        class FakeClient:
            model = "test-model"

            def structured(self, **kwargs: object) -> dict[str, object]:
                document = json.loads(str(kwargs["input_text"]))["documents"][0]
                return {
                    "events": [{
                        "event_key": "content_issues 2026-08-28_to-2026-09-01",
                        "input_ids": [document["input_id"]],
                        "title": "콘텐츠 문제 및 패치 안내",
                        "summary": "공식 공지에서 콘텐츠 문제와 수정 패치를 안내했다.",
                        "category": "NOTICE", "severity": "LOW", "bm_item_types": [],
                        "pm_terms": [], "pm_rationale": "", "severity_reason": "일반적인 문제 현상 안내다.",
                        "source_conflicts": [],
                    }],
                    "excluded_inputs": [],
                }

        now = datetime(2026, 8, 27, tzinfo=KST)
        notice = CollectedNotice("epic-seven", "https://example.com/1", "공지", now, now, "본문", content_hash("본문"))
        signal = analyze_notices_with_report(FakeClient(), (notice,)).signals[0]  # type: ignore[arg-type]
        self.assertEqual(signal.event_key, "content-issues-2026-08-28-to-2026-09-01")

    def test_same_event_key_merges_across_bounded_batches(self) -> None:
        class FakeClient:
            model = "test-model"

            def __init__(self) -> None:
                self.calls = 0

            def structured(self, **kwargs: object) -> dict[str, object]:
                self.calls += 1
                documents = json.loads(str(kwargs["input_text"]))["documents"]
                return {
                    "events": [{
                        "event_key": "shared-update-2026-08-27",
                        "input_ids": [item["input_id"] for item in documents],
                        "title": "공통 업데이트", "summary": "여러 공식 문서가 같은 업데이트를 다룬다.",
                        "category": "UPDATE", "severity": "MEDIUM", "bm_item_types": [],
                        "pm_terms": [], "pm_rationale": "", "severity_reason": "업데이트 안내다.",
                        "source_conflicts": [],
                    }],
                    "excluded_inputs": [],
                }

        now = datetime(2026, 8, 27, tzinfo=KST)
        notices = tuple(
            CollectedNotice(
                "epic-seven", f"https://example.com/{index}", f"공지 {index}", now, now,
                f"본문 {index}", content_hash(f"본문 {index}"),
            )
            for index in range(13)
        )
        client = FakeClient()
        outcome = analyze_notices_with_report(client, notices)  # type: ignore[arg-type]
        self.assertEqual(client.calls, 3)
        self.assertEqual(len(outcome.signals), 1)
        self.assertEqual(len(outcome.signals[0].evidence), 13)

    def test_analysis_cache_reuses_unchanged_game(self) -> None:
        class FakeClient:
            model = "test-model"

            def __init__(self) -> None:
                self.calls = 0

            def structured(self, **kwargs: object) -> dict[str, object]:
                self.calls += 1
                document = json.loads(str(kwargs["input_text"]))["documents"][0]
                return {
                    "events": [{
                        "event_key": "notice-2026-08-27", "input_ids": [document["input_id"]],
                        "title": "공지", "summary": "공식 공지다.", "category": "NOTICE", "severity": "LOW",
                        "bm_item_types": [], "pm_terms": [], "pm_rationale": "", "severity_reason": "일반 안내다.",
                        "source_conflicts": [],
                    }],
                    "excluded_inputs": [],
                }

        now = datetime(2026, 8, 27, tzinfo=KST)
        notice = CollectedNotice("mabinogi-mobile", "https://example.com/1", "공지", now, now, "본문", content_hash("본문"))
        client = FakeClient()
        with tempfile.TemporaryDirectory() as directory:
            state = StateStore(Path(directory))
            first = analyze_notices_with_report(client, (notice,), state=state)  # type: ignore[arg-type]
            second = analyze_notices_with_report(client, (notice,), state=state)  # type: ignore[arg-type]
        self.assertEqual(client.calls, 1)
        self.assertEqual(first.metrics["api_call_count"], 1)
        self.assertEqual(second.metrics["api_call_count"], 0)
        self.assertEqual(second.metrics["cache_hit_games"], ["mabinogi-mobile"])

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

    def test_saved_empty_collection_is_a_successful_coverage_gap(self) -> None:
        payload = {
            "notices": [],
            "videos": [],
            "coverage_gaps": [{"game_id": "mabinogi-mobile", "reason": "no recent evidence"}],
        }
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

        self.assertEqual(result["analysis_status"], "completed_no_evidence")
        self.assertEqual(result["input_count"], 0)
        self.assertEqual(result["signal_count"], 0)
        self.assertEqual(result["analysis_metrics"]["api_call_count"], 0)
        self.assertEqual(result["coverage_gaps"], payload["coverage_gaps"])


if __name__ == "__main__":
    unittest.main()
