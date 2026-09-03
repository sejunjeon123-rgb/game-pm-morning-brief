from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime
from pathlib import Path

from app.config import load_project_config
from player_live_watch.analyzer import analyze_player_evidence
from player_live_watch.common_collector import collect_player_live_evidence
from player_live_watch.collector import collect_dcinside_posts
from player_live_watch.dcinside_adapter import listing_page_url, parse_body, parse_listing
from player_live_watch.models import (
    CollectedPlayerEvidence,
    EvidenceClassification,
    classification_for_role,
)
from player_live_watch.runner import analyze_player_live_collection_file
from player_live_watch.youtube_adapter import parse_official_youtube_feed
from shared.http_client import HttpClientError, HttpResponse
from shared.state_store import StateStore
from shared.time_utils import KST


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def _evidence(
    *,
    evidence_id: str,
    classification: EvidenceClassification,
    source_type: str,
    source_id: str,
    host: str,
    title: str,
    text: str,
    published_at: datetime,
) -> CollectedPlayerEvidence:
    return CollectedPlayerEvidence(
        evidence_id=evidence_id,
        game_id="mabinogi-mobile",
        source_id=source_id,
        platform="YouTube" if classification is EvidenceClassification.OFFICIAL_FACT else "디시인사이드",
        source_type=source_type,
        evidence_role=(
            "OFFICIAL_FACT"
            if classification is EvidenceClassification.OFFICIAL_FACT
            else "PLAYER_REACTION"
        ),
        classification=classification,
        url=f"https://{host}/item/{evidence_id}",
        source_host=host,
        title=title,
        published_at=published_at,
        collected_at=datetime(2026, 9, 1, 8, 10, tzinfo=KST),
        normalized_text=text,
        content_hash=(evidence_id * 64)[:64],
        content_availability="FULL_TEXT",
    )


class DCInsideAdapterTests(unittest.TestCase):
    def test_configured_roles_define_evidence_boundary(self) -> None:
        self.assertEqual(
            classification_for_role("OFFICIAL_FACT"),
            EvidenceClassification.OFFICIAL_FACT,
        )
        self.assertEqual(
            classification_for_role("PLAYER_REACTION"),
            EvidenceClassification.PLAYER_CLAIM,
        )
        self.assertEqual(
            classification_for_role("CREATOR_ANALYSIS"),
            EvidenceClassification.CREATOR_ANALYSIS,
        )
        self.assertEqual(
            classification_for_role("unexpected-role"),
            EvidenceClassification.UNKNOWN,
        )

    def test_listing_omits_notice_wrong_gallery_and_writer(self) -> None:
        html = (FIXTURES / "dcinside_listing.html").read_text(encoding="utf-8")
        base = "https://gall.dcinside.com/mgallery/board/lists/?id=mabinogimobile"
        items = parse_listing("mabinogi-mobile", "mabinogi-mobile-dcinside", base, html)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "업데이트 후 전투가 멈추는 현상")
        self.assertEqual(items[0].comment_count, 7)
        self.assertEqual(items[0].view_count, 1234)
        self.assertEqual(items[0].recommendation_count, 12)
        self.assertNotIn("private-writer", repr(items[0]))
        self.assertEqual(
            items[0].url,
            "https://gall.dcinside.com/mgallery/board/view/?id=mabinogimobile&no=101",
        )

    def test_body_extracts_only_write_div(self) -> None:
        html = (FIXTURES / "dcinside_detail.html").read_text(encoding="utf-8")
        body = parse_body(html)
        self.assertIn("전투 진입 시 멈춤 현상", body)
        self.assertNotIn("private-writer", body)
        self.assertNotIn("댓글 작성자", body)
        self.assertNotIn("ignore-this", body)

    def test_listing_page_url_preserves_gallery_id(self) -> None:
        value = listing_page_url(
            "https://gall.dcinside.com/mgallery/board/lists/?id=mabinogimobile",
            2,
        )
        self.assertIn("id=mabinogimobile", value)
        self.assertIn("page=2", value)

    def test_collector_writes_privacy_minimized_post(self) -> None:
        listing = (FIXTURES / "dcinside_listing.html").read_bytes()
        detail = (FIXTURES / "dcinside_detail.html").read_bytes()

        class FixtureClient:
            listing_attempts = 0

            def get(self, url: str, *, headers: object = None) -> HttpResponse:
                if "/board/lists/" in url:
                    if "page=2" in url:
                        body = b"<html></html>"
                    else:
                        self.listing_attempts += 1
                        body = b"<html><body>temporary shell</body></html>" if self.listing_attempts == 1 else listing
                    return HttpResponse(url, 200, {"Content-Type": "text/html; charset=utf-8"}, body)
                return HttpResponse(url, 200, {"Content-Type": "text/html; charset=utf-8"}, detail)

        config = load_project_config(ROOT)
        with tempfile.TemporaryDirectory() as directory:
            report = collect_dcinside_posts(
                config,
                StateStore(Path(directory)),
                ("mabinogi-mobile",),
                client=FixtureClient(),  # type: ignore[arg-type]
                max_listing_pages=2,
                max_details_per_game=5,
                detail_workers=1,
                collected_at=datetime(2026, 9, 1, 8, 10, tzinfo=KST),
            )
        self.assertEqual(len(report["posts"]), 1)
        self.assertEqual(report["coverage_gaps"], [])
        self.assertEqual(report["posts"][0]["source_type"], "PUBLIC_COMMUNITY")
        self.assertEqual(report["posts"][0]["content_availability"], "FULL_TEXT")
        self.assertEqual(report["metrics"]["mabinogi-mobile"]["semantic_retry_count"], 2)
        self.assertNotIn("private-writer", str(report))

    def test_collector_prefetches_each_game_before_detail_reads(self) -> None:
        listing = (FIXTURES / "dcinside_listing.html").read_bytes()
        detail = (FIXTURES / "dcinside_detail.html").read_bytes()

        class OrderedClient:
            def __init__(self) -> None:
                self.urls: list[str] = []

            def get(self, url: str, *, headers: object = None) -> HttpResponse:
                self.urls.append(url)
                if "/board/lists/" in url:
                    body = (
                        listing.replace(b"mabinogimobile", b"blackdesertmobile")
                        if "blackdesertmobile" in url
                        else listing
                    )
                    return HttpResponse(
                        url,
                        200,
                        {"Content-Type": "text/html; charset=utf-8"},
                        body,
                    )
                return HttpResponse(
                    url,
                    200,
                    {"Content-Type": "text/html; charset=utf-8"},
                    detail,
                )

        client = OrderedClient()
        config = load_project_config(ROOT)
        with tempfile.TemporaryDirectory() as directory:
            report = collect_dcinside_posts(
                config,
                StateStore(Path(directory)),
                ("mabinogi-mobile", "black-desert-mobile"),
                client=client,  # type: ignore[arg-type]
                max_listing_pages=1,
                max_details_per_game=1,
                detail_workers=1,
                collected_at=datetime(2026, 9, 1, 8, 10, tzinfo=KST),
            )

        self.assertTrue(all("/board/lists/" in url for url in client.urls[:2]))
        self.assertEqual({post["game_id"] for post in report["posts"]}, {
            "mabinogi-mobile",
            "black-desert-mobile",
        })

    def test_collector_preserves_title_when_detail_is_unavailable(self) -> None:
        listing = (FIXTURES / "dcinside_listing.html").read_bytes()

        class TitleOnlyClient:
            def get(self, url: str, *, headers: object = None) -> HttpResponse:
                if "/board/lists/" in url:
                    return HttpResponse(
                        url,
                        200,
                        {"Content-Type": "text/html; charset=utf-8"},
                        listing,
                    )
                raise HttpClientError("detail unavailable")

        config = load_project_config(ROOT)
        with tempfile.TemporaryDirectory() as directory:
            report = collect_dcinside_posts(
                config,
                StateStore(Path(directory)),
                ("mabinogi-mobile",),
                client=TitleOnlyClient(),  # type: ignore[arg-type]
                max_listing_pages=1,
                max_details_per_game=1,
                detail_workers=1,
                collected_at=datetime(2026, 9, 1, 8, 10, tzinfo=KST),
            )

        self.assertEqual(len(report["posts"]), 1)
        self.assertEqual(report["posts"][0]["content_availability"], "TITLE_ONLY")
        self.assertEqual(report["metrics"]["mabinogi-mobile"]["title_only_count"], 1)
        self.assertIn("1 of 1 selected DCInside detail bodies", report["coverage_gaps"][0]["reason"])
        self.assertNotIn("/board/view/", report["coverage_gaps"][0]["reason"])

    def test_official_youtube_is_fact_not_player_reaction(self) -> None:
        xml = (FIXTURES / "youtube_feed.xml").read_text(encoding="utf-8")
        source = {
            "source_id": "trickcal-revive-official-youtube",
            "platform": "YouTube",
            "source_type": "OFFICIAL_YOUTUBE",
            "evidence_role": "OFFICIAL_FACT",
        }
        items = parse_official_youtube_feed(
            game_id="trickcal-revive",
            source=source,
            xml_text=xml,
            collected_at=datetime(2026, 9, 1, 8, 10, tzinfo=KST),
            filter_terms=("트릭컬",),
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].classification, EvidenceClassification.OFFICIAL_FACT)
        self.assertEqual(items[0].evidence_role, "OFFICIAL_FACT")

    def test_common_collector_preserves_fact_and_player_claim(self) -> None:
        listing = (FIXTURES / "dcinside_listing.html").read_bytes()
        detail = (FIXTURES / "dcinside_detail.html").read_bytes()
        feed = (FIXTURES / "youtube_feed.xml").read_bytes()

        class FixtureClient:
            def get(self, url: str, *, headers: object = None) -> HttpResponse:
                if "youtube.com/feeds/" in url:
                    return HttpResponse(url, 200, {"Content-Type": "application/atom+xml"}, feed)
                if "/board/lists/" in url:
                    body = b"<html></html>" if "page=2" in url else listing
                    return HttpResponse(url, 200, {"Content-Type": "text/html; charset=utf-8"}, body)
                return HttpResponse(url, 200, {"Content-Type": "text/html; charset=utf-8"}, detail)

        config = load_project_config(ROOT)
        with tempfile.TemporaryDirectory() as directory:
            report = collect_player_live_evidence(
                config,
                StateStore(Path(directory)),
                ("mabinogi-mobile",),
                client=FixtureClient(),  # type: ignore[arg-type]
                collected_at=datetime(2026, 9, 1, 8, 10, tzinfo=KST),
                max_listing_pages=2,
                max_details_per_game=5,
                detail_workers=1,
            )
        classifications = {item["classification"] for item in report["evidence"]}
        self.assertEqual(classifications, {"OFFICIAL_FACT", "PLAYER_CLAIM"})
        self.assertEqual(report["classification_counts"]["OFFICIAL_FACT"], 2)
        self.assertEqual(report["classification_counts"]["PLAYER_CLAIM"], 1)
        self.assertNotIn("private-writer", str(report))
        self.assertNotIn("writer", str(report).casefold())


class PlayerLiveAnalyzerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.official = _evidence(
            evidence_id="official1",
            classification=EvidenceClassification.OFFICIAL_FACT,
            source_type="OFFICIAL_YOUTUBE",
            source_id="mabinogi-mobile-official-youtube",
            host="www.youtube.com",
            title="점검 완료 안내",
            text="공식 채널에서 점검 완료와 수정 내용을 안내했다.",
            published_at=datetime(2026, 9, 1, 0, 0, tzinfo=KST),
        )
        self.claim = _evidence(
            evidence_id="claim1",
            classification=EvidenceClassification.PLAYER_CLAIM,
            source_type="PUBLIC_COMMUNITY",
            source_id="mabinogi-mobile-dcinside",
            host="gall.dcinside.com",
            title="점검 후에도 멈춤",
            text="점검 이후에도 전투 중 멈춤을 경험했다는 게시글이다.",
            published_at=datetime(2026, 9, 1, 8, 0, tzinfo=KST),
        )

    @staticmethod
    def _valid_result(input_ids: list[str]) -> dict[str, object]:
        return {
            "issues": [{
                "issue_key": "combat-freeze-after-maintenance",
                "input_ids": input_ids,
                "source_signal_ids": ["sig-maintenance"],
                "title": "점검 이후 전투 멈춤 주장",
                "summary": "공식 수정 안내 이후에도 일부 이용자 게시글에서 전투 멈춤 경험이 보고됐다.",
                "topic": "BUG",
                "reaction": "NEGATIVE",
                "intensity": "MEDIUM",
                "trend": "EMERGING",
                "confidence": "HIGH",
                "observed_facts": ["공식 채널에서 점검 완료와 수정 내용을 안내했다."],
                "player_claims": ["일부 이용자 게시글에서 전투 중 멈춤 경험이 보고됐다."],
                "analysis": ["공식 조치 이후에도 같은 현상이 남았는지 추가 확인이 필요하다."],
                "unknowns": ["동일 현상의 실제 발생 범위와 재현 조건은 공개 자료로 확인되지 않았다."],
                "pm_terms": ["Retention", "TS"],
                "pm_rationale": "재방문과 이용 시간을 내부 Retention 및 TS 지표로 확인할 필요가 있다.",
                "live_risk": "반복 발생 시 전투 경험과 서비스 신뢰에 영향을 줄 가능성이 있다.",
                "recommended_checks": ["점검 이후 오류 로그와 전투 구간별 재현 여부를 확인한다."],
            }],
            "excluded_inputs": [],
        }

    def test_structured_analysis_preserves_fact_and_claim_boundary(self) -> None:
        test_case = self

        class FakeClient:
            model = "test-model"

            def structured(self, **kwargs: object) -> dict[str, object]:
                inputs = json.loads(str(kwargs["input_text"]))["evidence"]
                return test_case._valid_result([item["input_id"] for item in inputs])

        outcome = analyze_player_evidence(
            FakeClient(),  # type: ignore[arg-type]
            (self.official, self.claim),
            source_signals=({
                "signal_id": "sig-maintenance",
                "game_id": "mabinogi-mobile",
                "title": "점검 안내",
                "summary": "공식 점검이 완료됐다.",
                "category": "MAINTENANCE",
                "severity": "HIGH",
            },),
        )
        self.assertEqual(len(outcome.insights), 1)
        insight = outcome.insights[0]
        self.assertEqual(insight.source_signal_ids, ("sig-maintenance",))
        self.assertEqual(len(insight.observed_facts), 1)
        self.assertEqual(len(insight.player_claims), 1)
        self.assertEqual(insight.routing.final_router, "pm-decision-lead")
        self.assertEqual(insight.pm_metric_context.terms, ("Retention", "TS"))

    def test_claim_only_cannot_be_promoted_to_observed_fact(self) -> None:
        class BadClient:
            model = "test-model"

            def structured(self, **kwargs: object) -> dict[str, object]:
                input_id = json.loads(str(kwargs["input_text"]))["evidence"][0]["input_id"]
                return {
                    "issues": [{
                        "issue_key": "unsupported-fact",
                        "input_ids": [input_id],
                        "source_signal_ids": [],
                        "title": "전투 멈춤 현상",
                        "summary": "이용자 게시글에서 전투 멈춤 현상이 언급됐다.",
                        "topic": "BUG", "reaction": "NEGATIVE", "intensity": "LOW",
                        "trend": "UNKNOWN", "confidence": "MEDIUM",
                        "observed_facts": ["전투 멈춤 현상이 공식적으로 확인됐다."],
                        "player_claims": ["이용자가 전투 멈춤을 경험했다고 주장했다."],
                        "analysis": ["추가 확인이 필요한 주장이다."],
                        "unknowns": ["공식 확인 여부는 알 수 없다."],
                        "pm_terms": [], "pm_rationale": "",
                        "live_risk": "반복될 경우 플레이 경험에 영향을 줄 가능성이 있다.",
                        "recommended_checks": ["오류 로그와 공식 확인 내용을 점검한다."],
                    }],
                    "excluded_inputs": [],
                }

        with self.assertRaisesRegex(ValueError, "observed_facts require OFFICIAL_FACT"):
            analyze_player_evidence(BadClient(), (self.claim,))  # type: ignore[arg-type]

    def test_official_fact_alone_cannot_be_labeled_player_reaction(self) -> None:
        class BadClient:
            model = "test-model"

            def structured(self, **kwargs: object) -> dict[str, object]:
                input_id = json.loads(str(kwargs["input_text"]))["evidence"][0]["input_id"]
                return {
                    "issues": [{
                        "issue_key": "official-video-reaction",
                        "input_ids": [input_id],
                        "source_signal_ids": [],
                        "title": "공식 점검 완료 안내",
                        "summary": "공식 채널에서 점검 완료 내용을 안내했다.",
                        "topic": "MAINTENANCE", "reaction": "POSITIVE", "intensity": "LOW",
                        "trend": "UNKNOWN", "confidence": "HIGH",
                        "observed_facts": ["공식 채널에서 점검 완료 내용을 안내했다."],
                        "player_claims": [],
                        "analysis": ["공식 안내만으로 이용자 반응을 판단할 수 없다."],
                        "unknowns": ["실제 이용자 반응은 확인되지 않았다."],
                        "pm_terms": [], "pm_rationale": "",
                        "live_risk": "현재 공개 자료에서는 별도 운영 위험이 확인되지 않았다.",
                        "recommended_checks": ["이용자 반응 자료가 수집되는지 추가 확인한다."],
                    }],
                    "excluded_inputs": [],
                }

        with self.assertRaisesRegex(ValueError, "reaction must be UNCLEAR"):
            analyze_player_evidence(BadClient(), (self.official,))  # type: ignore[arg-type]

    def test_completeness_failure_retries_once(self) -> None:
        test_case = self

        class CorrectingClient:
            model = "test-model"

            def __init__(self) -> None:
                self.calls = 0

            def structured(self, **kwargs: object) -> dict[str, object]:
                self.calls += 1
                inputs = json.loads(str(kwargs["input_text"]))["evidence"]
                if self.calls == 1:
                    return {"issues": [], "excluded_inputs": []}
                return test_case._valid_result([item["input_id"] for item in inputs])

        client = CorrectingClient()
        outcome = analyze_player_evidence(
            client,  # type: ignore[arg-type]
            (self.official, self.claim),
            source_signals=({"signal_id": "sig-maintenance", "game_id": "mabinogi-mobile"},),
        )
        self.assertEqual(client.calls, 2)
        self.assertEqual(outcome.metrics["validation_retry_count"], 1)

    def test_optional_metric_context_and_unknown_signal_link_are_sanitized(self) -> None:
        class NoisyClient:
            model = "test-model"

            def __init__(self) -> None:
                self.calls = 0

            def structured(self, **kwargs: object) -> dict[str, object]:
                self.calls += 1
                input_id = json.loads(str(kwargs["input_text"]))["evidence"][0]["input_id"]
                return {
                    "issues": [{
                        "issue_key": "combat-freeze-claim",
                        "input_ids": [input_id],
                        "source_signal_ids": ["invented-signal"],
                        "title": "전투 멈춤 경험 주장",
                        "summary": "이용자 게시글에서 전투 멈춤 경험이 보고됐다.",
                        "topic": "BUG", "reaction": "NEGATIVE", "intensity": "MEDIUM",
                        "trend": "UNKNOWN", "confidence": "MEDIUM",
                        "observed_facts": [],
                        "player_claims": ["이용자가 전투 중 멈춤을 경험했다고 주장했다."],
                        "analysis": ["공개 게시글만으로 실제 발생 범위를 판단할 수 없다."],
                        "unknowns": ["공식 확인 여부와 재현 조건은 알 수 없다."],
                        "pm_terms": ["ARPPU"],
                        "pm_rationale": "전투 오류와 관련된 내부 지표를 확인할 필요가 있다.",
                        "live_risk": "반복될 경우 플레이 경험에 영향을 줄 가능성이 있다.",
                        "recommended_checks": ["오류 로그와 공식 확인 내용을 점검한다."],
                    }],
                    "excluded_inputs": [],
                }

        client = NoisyClient()
        outcome = analyze_player_evidence(client, (self.claim,))  # type: ignore[arg-type]

        self.assertEqual(client.calls, 1)
        self.assertEqual(outcome.insights[0].source_signal_ids, ())
        self.assertEqual(outcome.insights[0].pm_metric_context.terms, ())
        self.assertEqual(outcome.insights[0].pm_metric_context.rationale, "")

    def test_low_value_single_source_chatter_is_excluded(self) -> None:
        class ChatterClient:
            model = "test-model"

            def structured(self, **kwargs: object) -> dict[str, object]:
                input_id = json.loads(str(kwargs["input_text"]))["evidence"][0]["input_id"]
                return {
                    "issues": [{
                        "issue_key": "costume-sharing",
                        "input_ids": [input_id],
                        "source_signal_ids": [],
                        "title": "코스튬 이미지 공유",
                        "summary": "이용자가 코스튬 이미지를 공유했다.",
                        "topic": "CONTENT", "reaction": "POSITIVE", "intensity": "LOW",
                        "trend": "UNKNOWN", "confidence": "LOW",
                        "observed_facts": [],
                        "player_claims": ["이용자가 꾸민 캐릭터 이미지를 게시했다."],
                        "analysis": ["일회성 이미지 공유 활동으로 확인된다."],
                        "unknowns": ["다른 이용자의 반응은 확인되지 않았다."],
                        "pm_terms": [], "pm_rationale": "",
                        "live_risk": "현재 공개 근거에서는 운영 위험이 확인되지 않았다.",
                        "recommended_checks": ["추가 조치 없이 관찰 대상으로만 유지한다."],
                    }],
                    "excluded_inputs": [],
                }

        outcome = analyze_player_evidence(ChatterClient(), (self.claim,))  # type: ignore[arg-type]

        self.assertEqual(outcome.insights, ())
        self.assertEqual(len(outcome.excluded_inputs), 1)
        self.assertIn("승격 기준", outcome.excluded_inputs[0]["reason"])

    def test_attribution_style_player_quote_fails_validation(self) -> None:
        test_case = self

        class QuotingClient:
            model = "test-model"

            def structured(self, **kwargs: object) -> dict[str, object]:
                inputs = json.loads(str(kwargs["input_text"]))["evidence"]
                result = test_case._valid_result([item["input_id"] for item in inputs])
                result["issues"][0]["player_claims"] = [
                    '"점검 후에도 멈췄다" — 이용자 게시글 원문'
                ]
                return result

        with self.assertRaisesRegex(ValueError, "must be paraphrased"):
            analyze_player_evidence(
                QuotingClient(),  # type: ignore[arg-type]
                (self.official, self.claim),
                source_signals=({"signal_id": "sig-maintenance", "game_id": "mabinogi-mobile"},),
            )

    def test_unquoted_em_dash_summary_is_not_treated_as_direct_quote(self) -> None:
        test_case = self

        class DashClient:
            model = "test-model"

            def structured(self, **kwargs: object) -> dict[str, object]:
                inputs = json.loads(str(kwargs["input_text"]))["evidence"]
                result = test_case._valid_result([item["input_id"] for item in inputs])
                result["issues"][0]["player_claims"] = [
                    "일부 게시물에서 전투 멈춤 — 점검 이후 재발 가능성이 보고됐다."
                ]
                return result

        outcome = analyze_player_evidence(
            DashClient(),  # type: ignore[arg-type]
            (self.official, self.claim),
            source_signals=({"signal_id": "sig-maintenance", "game_id": "mabinogi-mobile"},),
        )
        self.assertEqual(len(outcome.insights), 1)

    def test_analysis_cache_reuses_unchanged_game(self) -> None:
        test_case = self

        class FakeClient:
            model = "test-model"

            def __init__(self) -> None:
                self.calls = 0

            def structured(self, **kwargs: object) -> dict[str, object]:
                self.calls += 1
                inputs = json.loads(str(kwargs["input_text"]))["evidence"]
                return test_case._valid_result([item["input_id"] for item in inputs])

        client = FakeClient()
        signals = ({"signal_id": "sig-maintenance", "game_id": "mabinogi-mobile"},)
        with tempfile.TemporaryDirectory() as directory:
            state = StateStore(Path(directory))
            first = analyze_player_evidence(
                client,  # type: ignore[arg-type]
                (self.official, self.claim), source_signals=signals, state=state,
            )
            second = analyze_player_evidence(
                client,  # type: ignore[arg-type]
                (self.official, self.claim), source_signals=signals, state=state,
            )
        self.assertEqual(client.calls, 1)
        self.assertEqual(first.metrics["api_call_count"], 1)
        self.assertEqual(second.metrics["api_call_count"], 0)
        self.assertEqual(second.metrics["cache_hit_games"], ["mabinogi-mobile"])

    def test_saved_collection_fails_closed_without_openai_config(self) -> None:
        item = self.claim
        payload = {
            "evidence": [{
                "evidence_id": item.evidence_id,
                "game_id": item.game_id,
                "source_id": item.source_id,
                "platform": item.platform,
                "source_type": item.source_type,
                "evidence_role": item.evidence_role,
                "classification": item.classification.value,
                "url": item.url,
                "source_host": item.source_host,
                "title": item.title,
                "published_at": item.published_at.isoformat(),
                "collected_at": item.collected_at.isoformat(),
                "normalized_text": item.normalized_text,
                "content_hash": item.content_hash,
                "content_availability": item.content_availability,
            }],
            "coverage_gaps": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "player_live_collection.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            old_key = os.environ.pop("OPENAI_API_KEY", None)
            old_model = os.environ.pop("OPENAI_MODEL", None)
            try:
                result = analyze_player_live_collection_file(path)
            finally:
                if old_key is not None:
                    os.environ["OPENAI_API_KEY"] = old_key
                if old_model is not None:
                    os.environ["OPENAI_MODEL"] = old_model
        self.assertEqual(result["analysis_status"], "blocked_missing_openai_configuration")
        self.assertEqual(result["input_count"], 1)

    def test_saved_collection_records_analysis_gap_after_bounded_validation_failure(self) -> None:
        item = self.claim
        payload = {
            "evidence": [{
                "evidence_id": item.evidence_id,
                "game_id": item.game_id,
                "source_id": item.source_id,
                "platform": item.platform,
                "source_type": item.source_type,
                "evidence_role": item.evidence_role,
                "classification": item.classification.value,
                "url": item.url,
                "source_host": item.source_host,
                "title": item.title,
                "published_at": item.published_at.isoformat(),
                "collected_at": item.collected_at.isoformat(),
                "normalized_text": item.normalized_text,
                "content_hash": item.content_hash,
                "content_availability": item.content_availability,
            }],
            "coverage_gaps": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "player_live_collection.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            old_key = os.environ.get("OPENAI_API_KEY")
            old_model = os.environ.get("OPENAI_MODEL")
            os.environ["OPENAI_API_KEY"] = "test-key"
            os.environ["OPENAI_MODEL"] = "test-model"
            try:
                with patch(
                    "player_live_watch.runner.analyze_player_evidence",
                    side_effect=ValueError("invalid model output"),
                ):
                    result = analyze_player_live_collection_file(path)
            finally:
                if old_key is None:
                    os.environ.pop("OPENAI_API_KEY", None)
                else:
                    os.environ["OPENAI_API_KEY"] = old_key
                if old_model is None:
                    os.environ.pop("OPENAI_MODEL", None)
                else:
                    os.environ["OPENAI_MODEL"] = old_model

        self.assertEqual(result["analysis_status"], "completed_with_analysis_gap")
        self.assertEqual(result["insight_count"], 0)
        self.assertEqual(result["coverage_gaps"][0]["source"], "PLAYER_LIVE_ANALYSIS")
        self.assertIn("UNKNOWN_VALIDATION_ERROR", result["coverage_gaps"][0]["reason"])
        self.assertNotIn("invalid model output", str(result))


if __name__ == "__main__":
    unittest.main()
