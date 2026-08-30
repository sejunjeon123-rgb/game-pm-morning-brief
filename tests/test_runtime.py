from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.config import load_project_config
from app.pipeline import brief_as_dict, build_preview_brief
from shared.notion_client import format_notion_page
from shared.slack_client import format_brief
from shared.state_store import StateStore


ROOT = Path(__file__).resolve().parents[1]


class RuntimeTests(unittest.TestCase):
    def test_config_and_preview_cover_eight_games(self) -> None:
        config = load_project_config(ROOT)
        self.assertFalse(config.runtime["delivery"]["live_delivery_enabled"])
        self.assertEqual(config.runtime["delivery"]["providers"], ["slack-incoming-webhook", "notion-api"])
        brief = brief_as_dict(build_preview_brief(config))
        self.assertEqual(len(brief["game_scope"]), 8)
        self.assertEqual(set(brief["game_scope"]), set(brief["no_material_signal_games"]))
        self.assertTrue(all(item.get("youtube_channel_id", "").startswith("UC") for item in config.sources))
        self.assertEqual(config.source_policy["priority"], ["OFFICIAL_HOMEPAGE", "OFFICIAL_COMMUNITY", "OFFICIAL_YOUTUBE"])

    def test_slack_payload_has_header(self) -> None:
        brief = brief_as_dict(build_preview_brief(load_project_config(ROOT)))
        payload = format_brief(brief)
        self.assertEqual(payload["blocks"][0]["type"], "header")

    def test_notion_payload_and_slack_link(self) -> None:
        brief = brief_as_dict(build_preview_brief(load_project_config(ROOT)))
        notion = format_notion_page(brief, "0123456789abcdef0123456789abcdef")
        self.assertEqual(notion["parent"]["type"], "page_id")
        self.assertEqual(notion["properties"]["title"]["type"], "title")
        slack = format_brief(brief, notion_url="https://www.notion.so/example")
        self.assertIn("Notion에서 전체 브리핑 보기", str(slack["blocks"]))

    def test_source_conflicts_are_visible_in_delivery_formats(self) -> None:
        brief = brief_as_dict(build_preview_brief(load_project_config(ROOT)))
        brief["decisions"] = [{
            "priority": "P1", "title": "점검 종료 시각 확인",
            "executive_summary": "공식 출처의 종료 시각이 서로 다릅니다.",
            "conflicts": ["홈페이지는 10:00, 공식 커뮤니티는 11:00 종료로 안내합니다."],
            "evidence": [],
        }]
        slack = format_brief(brief)
        self.assertIn("⚠️ 출처 차이", str(slack["blocks"]))
        notion = format_notion_page(brief, "0123456789abcdef0123456789abcdef")
        self.assertIn("⚠️ 출처 차이", str(notion["children"]))

    def test_state_store_is_atomic_and_stable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory))
            self.assertTrue(store.write("runs/latest_success", {"ok": True}))
            self.assertFalse(store.write("runs/latest_success", {"ok": True}))
            self.assertEqual(store.read("runs/latest_success"), {"ok": True})
            json.loads((Path(directory) / "runs" / "latest_success.json").read_text(encoding="utf-8"))

    def test_state_store_rejects_escape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                StateStore(Path(directory)).write("../secret", {})


if __name__ == "__main__":
    unittest.main()
