"""Notion page formatter and standard-library API delivery adapter."""

from __future__ import annotations

import json
import re
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


NOTION_API_VERSION = "2026-03-11"
NOTION_PAGES_ENDPOINT = "https://api.notion.com/v1/pages"
_NOTION_ID = re.compile(r"^[0-9a-fA-F]{32}$")


class NotionDeliveryError(RuntimeError):
    pass


def _rich_text(content: str, *, link: str | None = None) -> list[dict[str, Any]]:
    value = content[:1900]
    text: dict[str, Any] = {"content": value}
    if link:
        text["link"] = {"url": link}
    return [{"type": "text", "text": text}]


def _paragraph(content: str) -> dict[str, Any]:
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": _rich_text(content)}}


def _heading(content: str, level: int = 2) -> dict[str, Any]:
    key = f"heading_{level}"
    return {"object": "block", "type": key, key: {"rich_text": _rich_text(content)}}


def _bullet(content: str) -> dict[str, Any]:
    return {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": _rich_text(content)}}


def format_notion_page(brief: dict[str, Any], parent_page_id: str) -> dict[str, Any]:
    normalized_parent = parent_page_id.replace("-", "")
    if not _NOTION_ID.fullmatch(normalized_parent):
        raise NotionDeliveryError("NOTION_PARENT_PAGE_ID must be a Notion page ID")
    date_label = str(brief["brief_date_kst"])
    title = f"{date_label} Game PM Morning Brief"
    children: list[dict[str, Any]] = [
        _paragraph(f"생성 시각: {brief['generated_at']} · 기준: Asia/Seoul · 핵심 8게임"),
        _heading("📌 Executive Summary"),
    ]
    summaries = brief.get("executive_summary") or ["오늘 확인된 긴급 사안은 없습니다."]
    children.extend(_bullet(str(item)) for item in summaries)

    decisions = brief.get("decisions", [])
    if brief.get("report_mode") == "compact-v1":
        # Nested item blocks retain all games, evidence and caveats without the
        # legacy 100-top-level-block truncation.
        for item in decisions:
            detail = []
            for label, field in (("✅ 확인됨", "observed_facts"), ("🗣️ 보고됨", "player_claims"),
                                 ("💡 가능성", "interpretation"), ("❓ 확인 필요", "unknowns"),
                                 ("⚠️ 출처 차이", "conflicts")):
                if item.get(field):
                    detail.append(_paragraph(label + "\n" + "\n".join(item[field])))
            for source in item.get("evidence", []):
                detail.append({"object": "block", "type": "paragraph", "paragraph": {
                    "rich_text": _rich_text(source["title"], link=source["url"])}})
            children.append({"object": "block", "type": "toggle", "toggle": {
                "rich_text": _rich_text(f"[{item['priority']}] {item['title']}"), "children": detail}})
        children.append(_heading("⚠️ 수집·분석 공백"))
        children.extend(_bullet(v) for v in brief.get("data_gaps", []))
        children.append(_paragraph("추가 중요 변경 없음: " + ", ".join(brief.get("no_material_signal_games", []))))
        children.append(_paragraph("Game Radar는 초기 안정화를 위해 보류 중입니다."))
        return {"parent": {"type": "page_id", "page_id": parent_page_id},
                "icon": {"type": "emoji", "emoji": "🎮"},
                "properties": {"title": {"type": "title", "title": _rich_text(title)}}, "children": children}
    children.append(_heading("🎯 PM Decisions"))
    if decisions:
        for item in decisions[:20]:
            children.append(_heading(f"[{item['priority']}] {item['title']}", 3))
            children.append(_paragraph(str(item.get("executive_summary", ""))))
            sections = (
                ("✅ 확인된 사실", item.get("observed_facts", [])),
                ("🗣️ 이용자 보고", item.get("player_claims", [])),
                ("💡 해석", item.get("interpretation", [])),
                ("❓ 확인 필요", item.get("unknowns", [])),
            )
            for label, values in sections:
                if values:
                    children.append(_heading(label, 3))
                    children.extend(_bullet(str(value)) for value in values[:10])
            conflicts = item.get("conflicts", [])
            if conflicts:
                children.append(_heading("⚠️ 출처 차이", 3))
                children.extend(_bullet(str(conflict)) for conflict in conflicts[:10])
            metric_checks = item.get("metric_checks", [])
            if metric_checks:
                children.append(_heading("📊 내부 KPI 확인", 3))
                children.extend(
                    _bullet(
                        f"{check.get('term')}: {check.get('question')}"
                        + (f" · 비교: {check.get('comparison_period')}" if check.get("comparison_period") else "")
                        + (f" · 구간: {check.get('segment')}" if check.get("segment") else "")
                    )
                    for check in metric_checks[:10]
                )
            actions = item.get("recommended_actions", [])
            if actions:
                children.append(_heading("🧭 권장 액션", 3))
                children.extend(
                    _bullet(
                        f"{action.get('action')} · 역할: {action.get('suggested_role')} · 시점: {action.get('timing')}"
                        f" · 재평가: {action.get('reassessment_condition')}"
                    )
                    for action in actions[:10]
                )
            for evidence in item.get("evidence", [])[:10]:
                url = str(evidence.get("url", ""))
                if url.startswith(("https://", "http://")):
                    children.append({
                        "object": "block",
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {"rich_text": _rich_text(str(evidence.get("title", url)), link=url)},
                    })
    else:
        children.append(_paragraph("현재 결정 항목이 없습니다."))

    radar = brief.get("radar_games", [])
    children.append(_heading("📡 Game Radar"))
    children.extend(_bullet(str(game)) for game in radar) if radar else children.append(_paragraph("등재된 외부 게임이 없습니다."))

    gaps = list(brief.get("coverage_gaps", [])) + list(brief.get("data_gaps", []))
    children.append(_heading("⚠️ Coverage & Data Gaps"))
    children.extend(_bullet(str(gap)) for gap in gaps) if gaps else children.append(_paragraph("보고된 coverage gap이 없습니다."))

    if len(children) > 100:
        children = children[:99] + [_paragraph("블록 한도로 인해 나머지 상세 항목은 생략되었습니다.")]
    return {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "icon": {"type": "emoji", "emoji": "🎮"},
        "properties": {"title": {"type": "title", "title": _rich_text(title)}},
        "children": children,
    }


def create_page(token: str, payload: dict[str, Any], *, timeout: float = 20.0, retries: int = 2) -> dict[str, str]:
    if not token:
        raise NotionDeliveryError("NOTION_TOKEN is required")
    request = Request(
        NOTION_PAGES_ENDPOINT,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": NOTION_API_VERSION,
        },
        method="POST",
    )
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
                page_id = result.get("id")
                page_url = result.get("url")
                if not isinstance(page_id, str) or not isinstance(page_url, str):
                    raise NotionDeliveryError("Notion response did not contain page id and URL")
                return {"page_id": page_id, "page_url": page_url}
        except HTTPError as exc:
            last_error = exc
            if exc.code == 429 and attempt < retries:
                retry_after = int(exc.headers.get("Retry-After", "1"))
                time.sleep(max(1, retry_after))
                continue
            if exc.code >= 500 and attempt < retries:
                time.sleep(2**attempt)
                continue
            raise NotionDeliveryError(f"Notion delivery failed with HTTP {exc.code}") from exc
        except (URLError, TimeoutError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(2**attempt)
                continue
            break
        except json.JSONDecodeError as exc:
            raise NotionDeliveryError("Notion returned invalid JSON") from exc
    raise NotionDeliveryError(f"Notion delivery failed: {type(last_error).__name__}") from last_error
