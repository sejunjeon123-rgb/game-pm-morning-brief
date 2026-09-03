from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
import unittest
from zoneinfo import ZoneInfo

from pm_decision_lead.analyzer import synthesize_morning_brief
from shared.notion_client import format_notion_page
from shared.slack_client import format_brief


KST = ZoneInfo("Asia/Seoul")
GAME_SCOPE = (
    "mabinogi-mobile", "black-desert-mobile", "odin", "seven-knights-rebirth",
    "nikke", "trickcal", "lineage-m", "epic-seven",
)


def evidence(evidence_id: str, source_type: str) -> dict[str, object]:
    return {
        "evidence_id": evidence_id,
        "source_type": source_type,
        "url": f"https://example.com/{evidence_id}",
        "title": "공식 업데이트 안내",
        "published_at": "2026-09-02T07:00:00+09:00",
        "collected_at": "2026-09-02T08:00:00+09:00",
        "content_hash": "a" * 64,
    }


def signal(*, severity: str = "MEDIUM") -> dict[str, object]:
    return {
        "signal_id": "signal-1", "event_key": "event-1", "game_id": "mabinogi-mobile",
        "title": "업데이트 안내", "summary": "신규 콘텐츠가 공식 발표되었습니다.",
        "category": "UPDATE", "severity": severity,
        "observed_at": "2026-09-02T08:00:00+09:00",
        "evidence": [evidence("official-1", "OFFICIAL_NOTICE")],
    }


def insight(*, linked: bool = True) -> dict[str, object]:
    return {
        "insight_id": "insight-1", "issue_key": "update-reaction",
        "game_id": "mabinogi-mobile", "title": "업데이트 반응",
        "summary": "일부 공개 게시물에서 보상 관련 질문이 보고되었습니다.",
        "topic": "REWARD", "reaction": "MIXED", "intensity": "MEDIUM",
        "trend": "EMERGING", "confidence": "MEDIUM",
        "observed_at": "2026-09-02T08:00:00+09:00",
        "evidence": [evidence("claim-1", "PUBLIC_COMMUNITY")],
        "source_signal_ids": ["signal-1"] if linked else [],
        "analysis_scope": "CORE",
    }


def valid_result() -> dict[str, object]:
    return {
        "decisions": [{
            "decision_key": "update-reward-check",
            "source_signal_ids": ["signal-1"],
            "source_insight_ids": ["insight-1"],
            "title": "업데이트 보상 문의 확인",
            "executive_summary": "신규 콘텐츠는 확인됐고 일부 이용자 문의의 실제 범위는 확인 필요합니다.",
            "priority": "P1", "disposition": "VERIFY", "confidence": "MEDIUM",
            "observed_facts": ["공식 공지에서 신규 콘텐츠 추가가 확인됐습니다."],
            "player_claims": ["일부 공개 게시물에서 보상 관련 질문이 보고됐습니다."],
            "interpretation": ["보상 안내의 이해 가능성을 점검할 필요가 있습니다."],
            "unknowns": ["문의가 전체 이용자에게 반복되는지는 확인되지 않았습니다."],
            "conflicts": [],
            "business_impact": ["PLAYER_EXPERIENCE"],
            "pm_terms": ["DAU"],
            "pm_rationale": "콘텐츠 이용 전후의 일간 활성 사용자 수인 DAU를 내부 지표로 확인할 필요가 있습니다.",
            "metric_checks": [{
                "term": "DAU", "question": "업데이트 전후 DAU를 같은 요일 기준으로 확인할 필요가 있습니까?",
                "comparison_period": "직전 동일 요일", "segment": "전체 이용자",
            }],
            "recommended_actions": [{
                "action": "반복 문의 유형을 확인합니다.", "suggested_role": "라이브 운영",
                "timing": "오늘", "dependency": "문의 분류 자료",
                "reassessment_condition": "반복 문의가 없거나 안내 보완 후 반응이 잦아들면 종료합니다.",
            }],
            "watch_conditions": ["동일 문의가 서로 다른 공개 출처에서 반복되면 우선순위를 재검토합니다."],
            "decision_rationale": "공식 변경은 확인됐지만 공개 반응의 대표성이 제한돼 같은 날 검증이 필요합니다.",
        }],
        "ignored_signal_ids": [],
        "ignored_insight_ids": [],
    }


class FakeClient:
    model = "test-model"

    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.responses = responses
        self.calls = 0

    def structured(self, **_: object) -> dict[str, object]:
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return deepcopy(response)


class PMDecisionLeadTests(unittest.TestCase):
    def test_builds_traceable_brief_and_preserves_player_claims(self) -> None:
        client = FakeClient([valid_result()])
        brief = synthesize_morning_brief(
            client,
            game_scope=GAME_SCOPE,
            signals=(signal(),),
            insights=(insight(),),
            generated_at=datetime(2026, 9, 2, 8, 10, tzinfo=KST),
        )
        self.assertEqual(len(brief.decisions), 1)
        self.assertEqual(brief.today_checks, (brief.decisions[0].decision_id,))
        self.assertEqual(len(brief.no_material_signal_games), 7)
        self.assertEqual(brief.decisions[0].player_claims[0][:2], "일부")
        self.assertEqual({item.evidence_id for item in brief.decisions[0].evidence}, {"official-1", "claim-1"})
        notion = format_notion_page(asdict(brief), "0123456789abcdef0123456789abcdef")
        slack = format_brief(asdict(brief))
        self.assertIn("이용자 보고", str(notion["children"]))
        self.assertIn("내부 KPI 확인", str(notion["children"]))
        self.assertIn("오늘 확인", str(slack["blocks"]))

    def test_retries_one_invalid_accounting_response(self) -> None:
        invalid = valid_result()
        invalid["ignored_signal_ids"] = ["signal-1"]
        client = FakeClient([invalid, valid_result()])
        synthesize_morning_brief(
            client, game_scope=GAME_SCOPE, signals=(signal(),), insights=(insight(),)
        )
        self.assertEqual(client.calls, 2)

    def test_drops_metric_check_when_metric_context_is_semantically_invalid(self) -> None:
        result = valid_result()
        result["decisions"][0]["pm_rationale"] = "관련 수치는 내부에서 확인할 필요가 있습니다."
        brief = synthesize_morning_brief(
            FakeClient([result]), game_scope=GAME_SCOPE,
            signals=(signal(),), insights=(insight(),),
        )
        decision = brief.decisions[0]
        self.assertEqual(decision.pm_metric_context.terms, ())
        self.assertEqual(decision.metric_checks, ())

    def test_drops_non_korean_optional_checks_and_actions(self) -> None:
        result = valid_result()
        result["decisions"][0]["metric_checks"][0]["question"] = "Check DAU after update"
        result["decisions"][0]["recommended_actions"][0]["suggested_role"] = "Live Ops"
        client = FakeClient([result])

        brief = synthesize_morning_brief(
            client, game_scope=GAME_SCOPE, signals=(signal(),), insights=(insight(),),
        )

        self.assertEqual(client.calls, 1)
        self.assertEqual(brief.decisions[0].metric_checks, ())
        self.assertEqual(brief.decisions[0].recommended_actions, ())

    def test_high_signal_requires_deep_dive_or_gap(self) -> None:
        with self.assertRaisesRegex(ValueError, "deep dive"):
            synthesize_morning_brief(
                FakeClient([valid_result()]),
                game_scope=GAME_SCOPE,
                signals=(signal(severity="HIGH"),),
                insights=(insight(linked=False),),
            )

    def test_rejects_p0_without_immediate_harm(self) -> None:
        invalid = valid_result()
        invalid["decisions"][0]["priority"] = "P0"
        invalid["decisions"][0]["disposition"] = "ESCALATE"
        with self.assertRaisesRegex(ValueError, "P0"):
            synthesize_morning_brief(
                FakeClient([invalid]), game_scope=GAME_SCOPE,
                signals=(signal(),), insights=(insight(),),
            )


if __name__ == "__main__":
    unittest.main()
