import unittest
from pathlib import Path

from app.config import load_project_config
from app.platform_preview_test import preview_brief
from shared.notion_client import format_notion_page
from shared.slack_client import format_brief
from shared.time_utils import now_kst


class PlatformPreviewTests(unittest.TestCase):
    def test_preview_is_clearly_synthetic_and_covers_eight_games(self):
        config = load_project_config(Path(__file__).resolve().parents[1])
        brief = preview_brief(config, now_kst())
        self.assertTrue(brief["test_mode"])
        self.assertEqual(len(brief["decisions"]), 8)
        self.assertTrue(all("실제 수집 결과가 아닌" in v["executive_summary"] for v in brief["decisions"]))
        notion = format_notion_page(brief, "0" * 32)
        slack = format_brief(brief, notion_url="https://www.notion.so/test")
        self.assertIn("[테스트] 게임 사업 동향 보고서", str(notion))
        self.assertIn("[테스트] 게임 사업 PM", str(slack))
        self.assertIn("https://www.notion.so/test", str(slack))
