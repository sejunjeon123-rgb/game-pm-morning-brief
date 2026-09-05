"""One-shot visual integration preview; no collection, AI, state, or scheduling."""
import os
from pathlib import Path

from app.config import load_project_config
from shared.notion_client import create_page, format_notion_page
from shared.slack_client import format_brief, post_webhook
from shared.time_utils import now_kst


def preview_brief(config, now):
    decisions = []
    for game in config.games:
        name = game.get("report_name", game["name_ko"])
        decisions.append({
            "game_id": game["id"], "title": f"{name} · 레이아웃 검증 항목",
            "executive_summary": "테스트: 실제 수집 결과가 아닌 플랫폼 표시 형식 검증용 문장입니다.",
            "priority": "P2", "confidence": "LOW", "observed_facts": [],
            "player_claims": [], "interpretation": [], "unknowns": [], "conflicts": [],
            "evidence": [],
        })
    return {
        "report_mode": "compact-v1", "test_mode": True,
        "brief_date_kst": now.date().isoformat(), "generated_at": now.isoformat(),
        "game_scope": list(config.game_ids),
        "executive_summary": [
            "테스트 보고서입니다. 실제 게임 소식·이용자 반응·사업 판단을 포함하지 않습니다.",
            "Notion 상세 보고서와 Slack 요약·링크 연결 형식만 확인합니다.",
        ],
        "decisions": decisions, "coverage_gaps": [], "data_gaps": [],
        "no_material_signal_games": [],
    }


def main():
    token = os.environ.get("NOTION_TOKEN", "")
    parent = os.environ.get("NOTION_PARENT_PAGE_ID", "")
    webhook = os.environ.get("SLACK_WEBHOOK_URL", "")
    if not token or not parent or not webhook:
        raise SystemExit("Required platform configuration is missing")
    config = load_project_config(Path(__file__).resolve().parents[1])
    brief = preview_brief(config, now_kst())
    notion = create_page(token, format_notion_page(brief, parent), retries=0)
    post_webhook(webhook, format_brief(brief, notion_url=notion["page_url"]))
    print("Notion and Slack preview test completed")
    print(notion["page_url"])


if __name__ == "__main__":
    main()
