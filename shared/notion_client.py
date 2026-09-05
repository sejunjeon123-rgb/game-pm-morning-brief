"""Notion page formatter and standard-library API delivery adapter."""

from __future__ import annotations

import json
import re
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from shared.report_layout import COLLECTION_SCOPE_NOTICE, report_games, empty_status, group_title


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


def _label(content: str) -> dict[str, Any]:
    block = _paragraph(content)
    block["paragraph"]["rich_text"][0]["annotations"] = {"bold": True}
    return block


def _callout(content: str, icon: str, color: str = "gray_background") -> dict[str, Any]:
    return {"object": "block", "type": "callout", "callout": {
        "rich_text": _rich_text(content), "icon": {"type": "emoji", "emoji": icon}, "color": color}}


def format_connection_test_page(parent_page_id: str, generated_at: str) -> dict[str, Any]:
    """Minimal page used only by the manually dispatched Notion connection test."""
    normalized_parent = parent_page_id.replace("-", "")
    if not _NOTION_ID.fullmatch(normalized_parent):
        raise NotionDeliveryError("NOTION_PARENT_PAGE_ID must be a Notion page ID")
    day = generated_at[:10]
    return {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "icon": {"type": "emoji", "emoji": "✅"},
        "properties": {"title": {"type": "title", "title": _rich_text(f"연결 테스트 | {day}")}},
        "children": [
            _callout("Notion 연결과 자식 페이지 생성 권한이 정상적으로 확인되었습니다.", "✅", "green_background"),
            _paragraph(f"확인 시각: {generated_at} · 게임 수집, OpenAI 호출 및 Slack 발송 없음"),
        ],
    }


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
        test_prefix = "[테스트] " if brief.get("test_mode") else ""
        children = [
            _paragraph(f"📅 기준일 {date_label}  ·  🕒 KST / 최근 7일  ·  🎮 8게임"),
            _paragraph(f"작성 기준 시각  {brief['generated_at']}"),
            {"object": "block", "type": "callout", "callout": {
                "rich_text": _rich_text("공식 발표 / 이용자 주장 / 해석을 구분합니다. P2·P3는 검토 구분이며, 긴급도 확정 판정이나 내부 성과 측정이 아닙니다."),
                "icon": {"type": "emoji", "emoji": "📌"}, "color": "gray_background"}},
            _heading("📋 01 · 핵심 요약"),
            *[_bullet(str(v)) for v in summaries],
            _heading("🗂️ 02 · 장르별 게임 보고"),
        ]
        last_group = None
        for game, items in report_games(brief):
            if game.get("report_group") != last_group:
                last_group = game.get("report_group")
                children.append({"object": "block", "type": "divider", "divider": {}})
                children.append(_heading(group_title(last_group)))
            children.append(_heading("🎮 " + game.get("report_name", game["name_ko"]), 3))
            if not items:
                children.append(_callout(empty_status(brief, game["id"]), "🔎"))
            for item in items:
                children.append(_callout(item["executive_summary"], "📌", "blue_background"))
                detail = [_paragraph(f"🏷️ 검토 구분 {item['priority']}  ·  판단 신뢰도 {item.get('confidence', 'LOW')}")]
                for label, field, missing in (
                    ("📣 공식 발표", "observed_facts", "연결된 공식 근거가 없습니다."),
                    ("💬 이용자 반응", "player_claims", "이 사안과 연결해 보고할 이용자 반응을 확보하지 못했습니다."),
                    ("💡 사업 관점 해석", "interpretation", "근거를 넘는 추가 해석은 제시하지 않았습니다."),
                    ("🔎 확인 필요 사항", "unknowns", "추가 확인 사항이 기재되지 않았습니다."),
                    ("⚖️ 출처 간 차이", "conflicts", "기록된 상충 내용은 없습니다. 출처 간 일치가 검증됐다는 뜻은 아닙니다."),
                ):
                    detail.append(_label(label))
                    detail.extend(_bullet(v) for v in item.get(field, []) or [missing])
                detail.append({"object": "block", "type": "divider", "divider": {}})
                detail.append(_label("🔗 근거 자료 · 게시일 / 출처 유형"))
                for source in item.get("evidence", []):
                    role = "공식" if source['source_type'].startswith('OFFICIAL') else "제작자 견해" if source['source_type'] == 'PUBLIC_CREATOR_YOUTUBE' else "유저 주장"
                    detail.append({"object": "block", "type": "paragraph", "paragraph": {
                        "rich_text": _rich_text(f"{str(source['published_at'])[:10]} · {role} · 원문 보기", link=source['url'])}})
                children.append({"object": "block", "type": "toggle", "toggle": {
                    "rich_text": _rich_text("📝 상세 보고 · " + item['title']), "children": detail}})
        children.append({"object": "block", "type": "divider", "divider": {}})
        children.append(_heading("🛡️ 03 · 수집 범위와 보고 한계"))
        children.append(_callout(COLLECTION_SCOPE_NOTICE, "🛡️"))
        return {"parent": {"type": "page_id", "page_id": parent_page_id},
                "icon": {"type": "emoji", "emoji": "🎮"},
                "properties": {"title": {"type": "title", "title": _rich_text(f"{test_prefix}게임 사업 동향 보고서 | {date_label}")}}, "children": children}
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
                if not isinstance(page_id, str) or not _NOTION_ID.fullmatch(page_id.replace("-", "")):
                    # Field names are safe to log; response values may contain user data.
                    fields = ",".join(sorted(str(key) for key in result))[:200]
                    raise NotionDeliveryError(f"Notion response did not contain a valid page id; fields={fields}")
                if not isinstance(page_url, str) or not page_url.startswith("https://"):
                    # A newly created page can be opened by its stable UUID even when a
                    # least-privilege response omits the convenience URL field.
                    page_url = f"https://www.notion.so/{page_id.replace('-', '')}"
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
