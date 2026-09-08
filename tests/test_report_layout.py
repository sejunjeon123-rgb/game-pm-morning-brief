import unittest
from shared.slack_client import format_brief
from shared.notion_client import format_notion_page
from shared.report_layout import game_headline_summaries, report_games


class LayoutTests(unittest.TestCase):
    def test_headline_summary_is_game_specific_and_conclusion_first(self):
        brief = {"game_scope": ["mabinogi-mobile", "black-desert-mobile"],
                 "decisions": [{"game_id": "black-desert-mobile", "title": "검은사막 모바일 · 신규 이벤트 확인",
                                "executive_summary": "확인됨: 신규 이벤트 일정이 안내됐습니다.",
                                "interpretation": ["참여 동선의 실제 반응을 확인할 필요가 있습니다."], "unknowns": []}],
                 "no_material_signal_games": ["mabinogi-mobile"], "coverage_gaps": []}
        summaries = game_headline_summaries(brief, detailed=True)
        self.assertTrue(summaries[0].startswith("마비노기 모바일 — 주요 변화 없음:"))
        self.assertIn("검은사막 모바일 — 신규 이벤트 확인:", summaries[1])
        self.assertIn("사업 관점 해석:", summaries[1])

    def test_slack_headlines_prioritize_four_games_with_decisions(self):
        decisions = [{"game_id": game, "title": f"{game} · 핵심 변화", "executive_summary": "확인됨: 공식 변경입니다.",
                      "priority": "P2", "confidence": "LOW", "observed_facts": [], "player_claims": [],
                      "interpretation": [], "unknowns": [], "conflicts": [], "evidence": []}
                     for game in ("black-desert-mobile", "odin-valhalla-rising", "lineage-m",
                                  "seven-knights-rebirth", "epic-seven")]
        brief = {"report_mode": "compact-v1", "brief_date_kst": "2026-09-08",
                 "generated_at": "2026-09-08T08:10:00+09:00", "decisions": decisions,
                 "game_scope": ["mabinogi-mobile", "black-desert-mobile", "odin-valhalla-rising", "lineage-m",
                                "seven-knights-rebirth", "epic-seven"], "coverage_gaps": []}
        text = str(format_brief(brief))
        self.assertIn("📋 핵심 요약", text)
        self.assertNotIn("마비노기 모바일 —", text.split("생활형 MMORPG")[0])
        self.assertNotIn("에픽세븐 — 핵심 변화", text.split("생활형 MMORPG")[0])

    def test_compact_platform_item_caps(self):
        decisions = []
        for index in range(3):
            decisions.append({"game_id": "mabinogi-mobile", "title": f"마비노기 항목 {index + 1}",
                              "executive_summary": "확인됨: 검토 항목입니다.", "priority": "P2",
                              "confidence": "LOW", "observed_facts": [], "player_claims": [],
                              "interpretation": [], "unknowns": [], "conflicts": [], "evidence": []})
        brief = {"report_mode": "compact-v1", "brief_date_kst": "2026-09-08",
                 "generated_at": "2026-09-08T08:10:00+09:00", "decisions": decisions,
                 "executive_summary": ["검토용 요약"], "game_scope": ["mabinogi-mobile"]}
        slack_text = str(format_brief(brief))
        notion_text = str(format_notion_page(brief, "0" * 32))
        self.assertIn("마비노기 항목 1", slack_text)
        self.assertNotIn("마비노기 항목 2", slack_text)
        self.assertIn("마비노기 항목 1", notion_text)
        self.assertIn("마비노기 항목 2", notion_text)
        self.assertNotIn("마비노기 항목 3", notion_text)

    def test_fixed_order_including_missing_games(self):
        brief = {"report_mode": "compact-v1", "brief_date_kst": "2026-09-04",
                 "generated_at": "2026-09-04T15:00:00+09:00", "decisions": [],
                 "executive_summary": ["검토용 요약"], "coverage_gaps": ["mabinogi-mobile"]}
        expected = ['마비노기 모바일', '검은사막 모바일', '오딘', '리니지M',
                    '세븐나이츠 리버스', '에픽세븐', '니케', '트릭컬 리바이브']
        self.assertEqual([g.get('report_name', g['name_ko']) for g,_ in report_games(brief)], expected)
        slack = format_brief(brief)
        text = '\n'.join(b['text']['text'] for b in slack['blocks'])
        self.assertEqual([text.index(name) for name in expected], sorted(text.index(name) for name in expected))
        notion = format_notion_page(brief, '0' * 32)
        names = [b['heading_3']['rich_text'][0]['text']['content'] for b in notion['children'] if b['type'] == 'heading_3']
        self.assertEqual(names, ['🎮 ' + name for name in expected])
        self.assertIn('🌿 생활형 MMORPG', str(notion))
        self.assertIn('🛡️ 03 · 수집 범위와 보고 한계', str(notion))
        self.assertIn('근거 부족', str(notion))
        self.assertLessEqual(len(notion['children']), 100)

    def test_youtube_diagnostics_are_not_repeated_in_reader_formats(self):
        brief = {"report_mode": "compact-v1", "brief_date_kst": "2026-09-05",
                 "generated_at": "2026-09-05T08:10:00+09:00", "decisions": [],
                 "executive_summary": ["검토용 요약"],
                 "coverage_gaps": ["mabinogi-mobile"],
                 "data_gaps": ["mabinogi-mobile: OFFICIAL_YOUTUBE HTTP_404 메타데이터 오류 3건"]}
        slack_text = str(format_brief(brief))
        notion_text = str(format_notion_page(brief, '0' * 32))
        for avoided in ("YouTube 수집 실패", "HTTP_404", "메타데이터 오류"):
            self.assertNotIn(avoided, slack_text)
            self.assertNotIn(avoided, notion_text)
        self.assertIn("YouTube는 게시일과 출처가 확인된 영상만 반영", notion_text)
        self.assertNotIn("수집 범위와 보고 한계", slack_text)
