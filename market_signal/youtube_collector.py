"""Collect recent uploads from verified official YouTube Atom feeds."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any
from xml.etree import ElementTree

from app.config import ProjectConfig
from market_signal.models import CollectedNotice
from market_signal.normalize import content_hash, normalize_text
from market_signal.youtube_fallback import collect_channel_fallback, fallback_summary
from shared.http_client import HttpClient, HttpClientError
from shared.state_store import StateStore
from shared.time_utils import ensure_kst, is_recent, now_kst


ATOM = "http://www.w3.org/2005/Atom"
YT = "http://www.youtube.com/xml/schemas/2015"
MEDIA = "http://search.yahoo.com/mrss/"


def _parse_feed(game_id: str, xml_text: str, collected_at: datetime, filter_terms: tuple[str, ...]) -> tuple[CollectedNotice, ...]:
    root = ElementTree.fromstring(xml_text)
    items: list[CollectedNotice] = []
    for entry in root.findall(f"{{{ATOM}}}entry"):
        video_id = entry.findtext(f"{{{YT}}}videoId", "").strip()
        title = normalize_text(entry.findtext(f"{{{ATOM}}}title", ""))
        published_text = entry.findtext(f"{{{ATOM}}}published", "")
        link_element = entry.find(f"{{{ATOM}}}link")
        url = link_element.get("href", "") if link_element is not None else ""
        description = normalize_text(entry.findtext(f"{{{MEDIA}}}group/{{{MEDIA}}}description", ""))
        searchable = f"{title} {description}".casefold()
        if filter_terms and not any(term.casefold() in searchable for term in filter_terms):
            continue
        if not video_id or not title or not published_text or not url.startswith("https://www.youtube.com/"):
            continue
        published_at = ensure_kst(datetime.fromisoformat(published_text.replace("Z", "+00:00")))
        if not is_recent(published_at, now=collected_at):
            continue
        normalized = normalize_text(f"{title}\n{description}")
        items.append(
            CollectedNotice(
                game_id=game_id,
                url=url,
                title=title,
                published_at=published_at,
                collected_at=collected_at,
                normalized_text=normalized,
                content_hash=content_hash(normalized),
                source_type="OFFICIAL_YOUTUBE",
            )
        )
    return tuple(items)


def collect_official_youtube(
    config: ProjectConfig,
    state: StateStore,
    game_ids: tuple[str, ...],
    *,
    client: HttpClient | None = None,
) -> dict[str, Any]:
    http = client or HttpClient(timeout=20, retries=2, backoff=1)
    source_by_game = {item["game_id"]: item for item in config.sources}
    collected_at = now_kst()
    previous_state = state.read("market-signal/youtube_hashes", {"videos": {}})
    records = dict(previous_state.get("videos", {}))
    videos: list[CollectedNotice] = []
    coverage_gaps: list[dict[str, str]] = []

    for game_id in game_ids:
        source = source_by_game[game_id]
        channel_id = source.get("youtube_channel_id", "")
        if not channel_id:
            coverage_gaps.append({"game_id": game_id, "source": "OFFICIAL_YOUTUBE", "reason": "verified channel ID is missing"})
            continue
        feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        filter_terms = tuple(source.get("youtube_filter_terms", ()))
        try:
            parsed = _parse_feed(game_id, http.get(feed_url).text(), collected_at, filter_terms)
        except (HttpClientError, ElementTree.ParseError, ValueError) as exc:
            coverage_gaps.append({"game_id": game_id, "source": "OFFICIAL_YOUTUBE", "code": exc.code if isinstance(exc, HttpClientError) else "FEED_PARSE_ERROR", "reason": f"YouTube feed collection failed: {type(exc).__name__}"})
            stats = {}
            try:
                parsed = collect_channel_fallback(http, source, collected_at, diagnostics=stats)
            except (HttpClientError, ValueError, KeyError, TypeError, AttributeError):
                parsed = ()
                stats["channel_failed"] = 1
            coverage_gaps.append({"game_id": game_id, "source": "OFFICIAL_YOUTUBE",
                                  "code": "BOUNDED_HTML_FALLBACK",
                                  "reason": f"RSS 대체 수집: 최대 3개 제목·설명 확인; {fallback_summary(stats)}; 자막·Shorts·라이브 미수집"})
        for video in parsed:
            previous = records.get(video.url, {})
            with_previous = CollectedNotice(
                game_id=video.game_id,
                url=video.url,
                title=video.title,
                published_at=video.published_at,
                collected_at=video.collected_at,
                normalized_text=video.normalized_text,
                content_hash=video.content_hash,
                previous_content_hash=previous.get("content_hash"),
                source_type=video.source_type,
            )
            videos.append(with_previous)
            records[video.url] = {
                "game_id": game_id,
                "title": video.title,
                "content_hash": video.content_hash,
                "first_seen_at": previous.get("first_seen_at", collected_at.isoformat()),
                "last_seen_at": collected_at.isoformat(),
                "published_at": video.published_at.isoformat(),
            }
    state.write("market-signal/youtube_hashes", {"videos": records})
    return {
        "videos": [asdict(item) | {"change_type": item.change_type} for item in videos],
        "coverage_gaps": coverage_gaps,
    }
