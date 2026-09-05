"""Slack Incoming Webhook formatting and delivery adapter."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from shared.report_layout import report_games, empty_status, group_title


class SlackDeliveryError(RuntimeError):
    pass


def format_brief(brief: dict[str, Any], *, notion_url: str | None = None) -> dict[str, Any]:
    if brief.get("report_mode") == "compact-v1":
        blocks = [{"type": "header", "text": {"type": "plain_text", "text": f"🎮 게임 사업 PM · {brief['brief_date_kst']}"}}]
        def section(text):
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": text}})
        section("새 글·수정 글 중심입니다. 유저 반응은 일부 공개 표본이며 긴급도 확정 판정은 포함하지 않습니다.")
        ordered = []
        for game, items in report_games(brief):
            ordered.append((game, items))
        last_group = None
        for game, items in ordered:
            if game.get("report_group") != last_group:
                last_group = game.get("report_group")
                section(f"*{group_title(last_group)}*")
            if not items:
                section(f"🎮 *{game.get('report_name', game['name_ko'])}*\n" + empty_status(brief, game["id"]))
            for item in items:
                section(_compact_item(item))
        if brief.get("coverage_gaps"):
            section("⚠️ 일부 출처의 수집·분석 공백이 있습니다. Notion 전체 보고서에서 범위와 한계를 확인해 주세요.")
        if notion_url:
            section(f"📚 <{notion_url}|Notion 전체 보고서>")
        return {"text": f"게임 사업 PM 보고서 {brief['brief_date_kst']}", "blocks": blocks}
    return _legacy_format(brief, notion_url)


def _compact_item(item):
            lines = [f"🎮 *{item['title']}*", item["executive_summary"]]
            if item.get("observed_facts") and item.get("player_claims"):
                lines.append("🗣️ 보고됨: " + item["player_claims"][0])
            lines.extend("⚠️ 출처 차이: " + v for v in item.get("conflicts", []))
            lines.extend("❓ 확인 필요: " + v for v in item.get("unknowns", []))
            if item.get("evidence"):
                source = next((e for e in item['evidence'] if e['source_type'].startswith('OFFICIAL')), item['evidence'][0])
                lines.append(f"<{source['url']}|근거 보기>")
            return "\n".join(lines)


def _legacy_format(brief, notion_url=None):
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
