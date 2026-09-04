from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.config import load_project_config
from app.daily import build_daily, collect_daily
from app.run import main
from shared.state_store import StateStore
from shared.slack_client import format_brief
from shared.notion_client import format_notion_page

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 4, 8, 10, tzinfo=ZoneInfo("Asia/Seoul"))


def document(game, *, role="OFFICIAL_FACT", hash_value="a" * 64):
    return {"game_id": game, "url": f"https://example.com/{game}/{role}",
            "title": "업데이트 안내", "published_at": NOW.isoformat(),
            "collected_at": NOW.isoformat(), "normalized_text": "신규 콘텐츠 업데이트가 안내됐습니다.",
            "content_hash": hash_value, "classification": role,
            "source_type": "OFFICIAL_NOTICE" if role == "OFFICIAL_FACT" else "PUBLIC_COMMUNITY"}


class FakeClient:
    def __init__(self, fail_first=False, boundary_error=False):
        self.calls = 0
        self.fail_first = fail_first
        self.boundary_error = boundary_error

    def structured(self, **kwargs):
        self.calls += 1
        if self.fail_first and self.calls == 1:
            raise ValueError("untrusted error must not leak")
        docs = json.loads(kwargs["input_text"])
        facts = [{"text": "신규 콘텐츠 업데이트가 안내됐습니다.", "evidence_ids": [d["evidence_id"]]}
                 for d in docs if d["classification"] == "OFFICIAL_FACT"]
        claims = [{"text": "일부 게시물에서 사용 경험이 보고됐습니다.", "evidence_ids": [d["evidence_id"]]}
                  for d in docs if d["classification"] == "PLAYER_CLAIM"]
        if self.boundary_error:
            facts, claims = claims, []
        return {"items": [{"title": "콘텐츠 업데이트 확인", "category": "UPDATE", "bm_types": [],
                           "facts": facts[:3], "claims": claims[:3], "interpretation": [],
                           "unknowns": ["실제 이용 범위는 확인이 필요합니다."], "conflicts": []}]}


class DailyTests(unittest.TestCase):
    def setUp(self):
        self.config = load_project_config(ROOT)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = StateStore(Path(self.tmp.name))
        self.collection = {"game_scope": self.config.game_ids,
                           "official": [document(g) for g in self.config.game_ids],
                           "players": [], "coverage_gaps": []}

    def test_eight_games_at_most_eight_calls_and_same_day_cache(self):
        client = FakeClient()
        first = build_daily(self.config, self.state, self.collection, client, now=NOW)
        second = build_daily(self.config, self.state, self.collection, client, now=NOW)
        self.assertEqual(client.calls, 8)
        self.assertEqual(len(first["brief"]["decisions"]), 8)
        self.assertEqual(len(second["brief"]["decisions"]), 8)
        self.assertEqual(second["metrics"]["api_call_count"], 0)
        self.assertNotIn("normalized_text", json.dumps(self.state.read("daily/summaries")))

    def test_unchanged_next_day_free_modified_reanalyzed(self):
        client = FakeClient()
        build_daily(self.config, self.state, self.collection, client, now=NOW)
        unchanged = build_daily(self.config, self.state, self.collection, client, now=NOW + timedelta(days=1))
        self.assertEqual(unchanged["metrics"]["api_call_count"], 0)
        self.collection["official"][0]["content_hash"] = "b" * 64
        modified = build_daily(self.config, self.state, self.collection, client, now=NOW + timedelta(days=1))
        self.assertEqual(modified["metrics"]["api_call_count"], 1)

    def test_one_failure_keeps_seven_games_and_no_paid_retry(self):
        client = FakeClient(fail_first=True)
        first = build_daily(self.config, self.state, self.collection, client, now=NOW)
        self.assertEqual(len(first["brief"]["decisions"]), 7)
        self.assertIn(self.config.game_ids[0], first["brief"]["coverage_gaps"])
        self.assertNotIn("untrusted", str(first))
        build_daily(self.config, self.state, self.collection, client, now=NOW)
        self.assertEqual(client.calls, 8)
        retry = build_daily(self.config, self.state, self.collection, client, now=NOW + timedelta(days=1))
        self.assertEqual(retry["metrics"]["api_call_count"], 1)

    def test_player_claim_cannot_become_fact(self):
        game = self.config.game_ids[0]
        self.collection["official"] = []
        self.collection["players"] = [document(game, role="PLAYER_CLAIM")]
        result = build_daily(self.config, self.state, self.collection, FakeClient(boundary_error=True), now=NOW)
        self.assertEqual(result["brief"]["decisions"], ())
        self.assertIn(game, result["brief"]["coverage_gaps"])

    def test_stale_and_unscanned_games_are_not_reported_as_clear(self):
        self.collection["game_scope"] = [self.config.game_ids[0]]
        for d in self.collection["official"]:
            d["published_at"] = (NOW - timedelta(days=8)).isoformat()
        result = build_daily(self.config, self.state, self.collection, FakeClient(), now=NOW)
        self.assertEqual(result["metrics"]["api_call_count"], 0)
        self.assertEqual(len(result["brief"]["coverage_gaps"]), 7)

    def test_disabled_automatic_does_not_collect_or_call_api(self):
        with patch("sys.argv", ["run", "--mode", "automatic"]), patch("app.run.collect_daily") as collect:
            self.assertEqual(main(), 0)
            collect.assert_not_called()

    def test_automatic_delivers_real_report_once_per_date(self):
        config = deepcopy(self.config)
        config.runtime["delivery"]["live_delivery_enabled"] = True
        argv = ["run", "--mode", "automatic", "--state-dir", self.tmp.name,
                "--output-dir", str(Path(self.tmp.name) / "out")]
        env = {"OPENAI_API_KEY": "test", "OPENAI_MODEL": "test", "SLACK_WEBHOOK_URL": "test",
               "NOTION_TOKEN": "test", "NOTION_PARENT_PAGE_ID": "0" * 32}
        with patch("sys.argv", argv), patch.dict("os.environ", env), \
             patch("app.run.load_project_config", return_value=config), \
             patch("app.run.collect_daily", return_value=self.collection), \
             patch("app.run.OpenAIResponsesClient", return_value=FakeClient()), \
             patch("app.daily.now_kst", return_value=NOW), \
             patch("app.run.create_page", return_value={"page_id": "page", "page_url": "https://www.notion.so/test"}) as notion, \
             patch("app.run.post_webhook") as slack:
            self.assertEqual(main(), 0)
            self.assertEqual(main(), 0)
        notion.assert_called_once()
        slack.assert_called_once()
        self.assertIn("마비노기 모바일", str(slack.call_args))
        self.assertIn("notion.so/test", str(slack.call_args))

    def test_notion_uncertainty_holds_slack_and_prevents_resend(self):
        from shared.notion_client import NotionDeliveryError
        config = deepcopy(self.config)
        config.runtime["delivery"]["live_delivery_enabled"] = True
        argv = ["run", "--mode", "automatic", "--state-dir", self.tmp.name,
                "--output-dir", str(Path(self.tmp.name) / "out")]
        env = {"OPENAI_API_KEY": "test", "OPENAI_MODEL": "test", "SLACK_WEBHOOK_URL": "test",
               "NOTION_TOKEN": "test", "NOTION_PARENT_PAGE_ID": "0" * 32}
        with patch("sys.argv", argv), patch.dict("os.environ", env), \
             patch("app.run.load_project_config", return_value=config), \
             patch("app.run.collect_daily", return_value=self.collection), \
             patch("app.run.OpenAIResponsesClient", return_value=FakeClient()), \
             patch("app.daily.now_kst", return_value=NOW), \
             patch("app.run.create_page", side_effect=NotionDeliveryError("timeout")) as notion, \
             patch("app.run.post_webhook") as slack:
            self.assertEqual(main(), 4)
            self.assertEqual(main(), 4)
        notion.assert_called_once()
        slack.assert_not_called()

    def test_both_formats_keep_all_eight_games(self):
        report = build_daily(self.config, self.state, self.collection, FakeClient(), now=NOW)
        brief = report["brief"]
        slack = format_brief(brief)
        notion = format_notion_page(brief, "0" * 32)
        for decision in brief["decisions"]:
            self.assertIn(decision["title"], str(slack))
            self.assertIn(decision["title"], str(notion))
        self.assertLessEqual(len(slack["blocks"]), 50)
        self.assertLessEqual(len(notion["children"]), 100)
        for block in slack["blocks"]:
            self.assertLessEqual(len(block["text"]["text"]), 3000)

    def test_collector_uses_small_bounds_and_single_youtube_pass(self):
        with patch("app.daily.collect_official_notices", return_value={"notices": [], "coverage_gaps": []}) as official, \
             patch("app.daily.collect_official_youtube", return_value={"videos": [], "coverage_gaps": []}) as youtube, \
             patch("app.daily.collect_dcinside_posts", return_value={"posts": [], "coverage_gaps": []}) as players:
            collect_daily(self.config, self.state, self.config.game_ids)
        self.assertEqual(official.call_args.kwargs["max_details_per_game"], 8)
        self.assertEqual(players.call_args.kwargs["max_details_per_game"], 5)
        youtube.assert_called_once()

    def test_skill_frontmatter_and_compact_contract_links(self):
        for name in ("market-signal", "player-live-watch", "pm-decision-lead"):
            text = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
            self.assertTrue(text.startswith("---\n"))
            frontmatter = text.split("---", 2)[1]
            fields = dict(line.split(":", 1) for line in frontmatter.strip().splitlines())
            self.assertEqual(fields["name"].strip(), name)
            self.assertTrue(fields["description"].strip())
            self.assertIn("compact-v1", text)
            self.assertIn("app/daily.py", text)
        self.assertTrue((ROOT / "docs" / "compact-runtime.md").is_file())


if __name__ == "__main__":
    unittest.main()
