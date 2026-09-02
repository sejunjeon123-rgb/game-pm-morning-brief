"""Slack Incoming Webhook formatting and delivery adapter."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class SlackDeliveryError(RuntimeError):
    pass


def format_brief(brief: dict[str, Any], *, notion_url: str | None = None) -> dict[str, Any]:
    date_label = brief["brief_date_kst"]
    summary = brief.get("executive_summary") or ["오늘 확인된 긴급 사안은 없습니다."]
    decisions = brief.get("decisions", [])
    radar = brief.get("radar_games", [])
    lines = [f"• {line}" for line in summary[:5]]
    if decisions:
        for item in decisions[:10]:
            icon = {"P0": "🚨", "P1": "🔴", "P2": "🟠", "P3": "🟡"}.get(item["priority"], "•")
            lines.append(f"{icon} *[{item['priority']}] {item['title']}* — {item.get('executive_summary', '')}")
            for conflict in item.get("conflicts", [])[:3]:
                lines.append(f"  ⚠️ 출처 차이: {conflict}")
    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": f"🎮 Game PM Morning Brief · {date_label}", "emoji": True}},
        {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": "🕗 매일 08:10 KST · 핵심 8게임"}]},
    ]
    if radar:
        blocks.insert(2, {"type": "section", "text": {"type": "mrkdwn", "text": "📡 *Game Radar*\n" + "\n".join(f"• {game}" for game in radar)}})
    decision_titles = {item.get("decision_id"): item.get("title", "") for item in decisions}
    checks = [decision_titles.get(item, item) for item in brief.get("today_checks", [])]
    watch = [decision_titles.get(item, item) for item in brief.get("watchlist", [])]
    gaps = [str(item) for item in brief.get("data_gaps", [])]
    operational: list[str] = []
    if checks:
        operational.append("✅ *오늘 확인*\n" + "\n".join(f"• {item}" for item in checks[:8]))
    if watch:
        operational.append("👀 *Watchlist*\n" + "\n".join(f"• {item}" for item in watch[:8]))
    if gaps:
        operational.append("⚠️ *데이터 공백*\n" + "\n".join(f"• {item}" for item in gaps[:8]))
    if operational:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n\n".join(operational)}})
    if notion_url:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"📚 <{notion_url}|Notion에서 전체 브리핑 보기>"}})
    return {"text": f"Game PM Morning Brief {date_label}", "blocks": blocks}


def post_webhook(webhook_url: str, payload: dict[str, Any], *, timeout: float = 15.0) -> None:
    if not webhook_url.startswith("https://hooks.slack.com/"):
        raise SlackDeliveryError("invalid Slack webhook URL")
    request = Request(
        webhook_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            if response.status != 200 or body.strip() != "ok":
                raise SlackDeliveryError(f"Slack delivery failed with HTTP {response.status}")
    except HTTPError as exc:
        raise SlackDeliveryError(f"Slack delivery failed with HTTP {exc.code}") from exc
    except (URLError, TimeoutError) as exc:
        raise SlackDeliveryError(f"Slack delivery failed: {exc}") from exc
