import unittest
from shared.slack_client import format_brief
from shared.notion_client import format_notion_page
from shared.report_layout import report_games


class LayoutTests(unittest.TestCase):
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
