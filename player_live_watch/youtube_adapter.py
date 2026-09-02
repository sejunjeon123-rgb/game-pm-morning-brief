"""Official YouTube RSS adapter for Player Live evidence context."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import hashlib
from typing import Any
from urllib.parse import urlparse
from xml.etree import ElementTree

from app.config import ProjectConfig
from market_signal.normalize import content_hash, normalize_text
from player_live_watch.models import (
    CollectedPlayerEvidence,
    classification_for_role,
)
from shared.http_client import HttpClient, HttpClientError
from shared.state_store import StateStore
from shared.time_utils import ensure_kst, is_recent, now_kst


ATOM = "http://www.w3.org/2005/Atom"
YT = "http://www.youtube.com/xml/schemas/2015"
MEDIA = "http://search.yahoo.com/mrss/"


def _evidence_id(source_id: str, url: str) -> str:
    digest = hashlib.sha256(f"{source_id}|{url}".encode("utf-8")).hexdigest()[:20]
    return f"ple-{digest}"


def parse_official_youtube_feed(
    *,
    game_id: str,
    source: dict[str, Any],
    xml_text: str,
    collected_at: datetime,
    filter_terms: tuple[str, ...] = (),
    previous_records: dict[str, Any] | None = None,
) -> tuple[CollectedPlayerEvidence, ...]:
    """Parse recent official uploads without treating them as player reaction."""

    records = previous_records or {}
    root = ElementTree.fromstring(xml_text)
    items: list[CollectedPlayerEvidence] = []
    for entry in root.findall(f"{{{ATOM}}}entry"):
        video_id = entry.findtext(f"{{{YT}}}videoId", "").strip()
        title = normalize_text(entry.findtext(f"{{{ATOM}}}title", ""))
        published_text = entry.findtext(f"{{{ATOM}}}published", "").strip()
        link = entry.find(f"{{{ATOM}}}link")
        url = link.get("href", "") if link is not None else ""
        description = normalize_text(
            entry.findtext(f"{{{MEDIA}}}group/{{{MEDIA}}}description", "")
        )
        searchable = f"{title} {description}".casefold()
        if filter_terms and not any(term.casefold() in searchable for term in filter_terms):
            continue
        if not video_id or not title or not published_text:
            continue
        if urlparse(url).hostname not in {"www.youtube.com", "youtube.com"}:
            continue
        published_at = ensure_kst(datetime.fromisoformat(published_text.replace("Z", "+00:00")))
        if not is_recent(published_at, now=collected_at):
            continue
        normalized = normalize_text(f"{title}\n{description}")
        previous = records.get(url, {})
        items.append(
            CollectedPlayerEvidence(
                evidence_id=_evidence_id(source["source_id"], url),
                game_id=game_id,
                source_id=source["source_id"],
                platform=source["platform"],
                source_type=source["source_type"],
                evidence_role=source["evidence_role"],
                classification=classification_for_role(source["evidence_role"]),
                url=url,
                source_host=urlparse(url).hostname or "",
                title=title,
                published_at=published_at,
                collected_at=collected_at,
                normalized_text=normalized,
                content_hash=content_hash(normalized),
                content_availability="FULL_TEXT" if description else "TITLE_ONLY",
                previous_content_hash=previous.get("content_hash"),
            )
        )
    return tuple(items)


def collect_official_youtube_evidence(
    config: ProjectConfig,
    state: StateStore,
    game_ids: tuple[str, ...],
    *,
    client: HttpClient | None = None,
    collected_at: datetime | None = None,
) -> dict[str, Any]:
    """Collect verified RSS-ready official channels for Player Live context."""

    http = client or HttpClient(timeout=20, retries=2, backoff=1)
    observed_at = collected_at or now_kst()
    market_sources = {item["game_id"]: item for item in config.sources}
    player_sources = {
        item["game_id"]: tuple(
            source
            for source in item["sources"]
            if source["source_type"] == "OFFICIAL_YOUTUBE"
            and source["collection_status"] == "RSS_READY"
        )
        for item in config.player_live_sources
    }
    previous_state = state.read("player-live/youtube_hashes", {"videos": {}})
    records = dict(previous_state.get("videos", {}))
    evidence: list[CollectedPlayerEvidence] = []
    gaps: list[dict[str, str]] = []
    metrics: dict[str, dict[str, int | bool]] = {}

    for game_id in game_ids:
        sources = player_sources.get(game_id, ())
        market_source = market_sources.get(game_id, {})
        channel_id = market_source.get("youtube_channel_id", "")
        if not sources or not channel_id:
            gaps.append(
                {
                    "game_id": game_id,
                    "source": "OFFICIAL_YOUTUBE",
                    "reason": "verified RSS-ready source or channel ID is missing",
                }
            )
            metrics[game_id] = {"accessible": False, "item_count": 0}
            continue
        source = sources[0]
        feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        try:
            response = http.get(feed_url)
            parsed = parse_official_youtube_feed(
                game_id=game_id,
                source=source,
                xml_text=response.text(),
                collected_at=observed_at,
                filter_terms=tuple(market_source.get("youtube_filter_terms", ())),
                previous_records=records,
            )
        except (HttpClientError, ElementTree.ParseError, KeyError, TypeError, ValueError) as exc:
            gaps.append(
                {
                    "game_id": game_id,
                    "source": source["source_id"],
                    "reason": f"official YouTube collection failed: {type(exc).__name__}",
                }
            )
            metrics[game_id] = {"accessible": False, "item_count": 0}
            continue
        for item in parsed:
            evidence.append(item)
            previous = records.get(item.url, {})
            records[item.url] = {
                "game_id": game_id,
                "source_id": item.source_id,
                "title": item.title,
                "content_hash": item.content_hash,
                "first_seen_at": previous.get("first_seen_at", observed_at.isoformat()),
                "last_seen_at": observed_at.isoformat(),
                "published_at": item.published_at.isoformat(),
            }
        metrics[game_id] = {"accessible": True, "item_count": len(parsed)}

    state.write("player-live/youtube_hashes", {"videos": records})
    return {
        "collected_at": observed_at,
        "game_scope": game_ids,
        "adapter": "official-youtube-rss-v1",
        "evidence": [
            asdict(item)
            | {
                "classification": item.classification.value,
                "change_type": item.change_type,
            }
            for item in evidence
        ],
        "coverage_gaps": gaps,
        "metrics": metrics,
    }
