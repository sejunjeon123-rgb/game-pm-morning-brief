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
    children.append(_heading("🎯 PM Decisions"))
    if decisions:
        for item in decisions[:20]:
            children.append(_heading(f"[{item['priority']}] {item['title']}", 3))
            children.append(_paragraph(str(item.get("executive_summary", ""))))
            conflicts = item.get("conflicts", [])
            if conflicts:
                children.append(_heading("⚠️ 출처 차이", 3))
                children.extend(_bullet(str(conflict)) for conflict in conflicts[:10])
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

    gaps = brief.get("coverage_gaps", [])
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
