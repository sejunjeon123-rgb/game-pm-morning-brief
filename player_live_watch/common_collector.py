"""Common Player Live collection orchestrator and evidence boundary."""

from __future__ import annotations

from datetime import datetime
import hashlib
from typing import Any
from urllib.parse import urlparse

from app.config import ProjectConfig
from player_live_watch.collector import collect_dcinside_posts
from player_live_watch.models import classification_for_role
from player_live_watch.youtube_adapter import collect_official_youtube_evidence
from shared.http_client import HttpClient
from shared.state_store import StateStore
from shared.time_utils import now_kst


def _evidence_id(source_id: str, url: str) -> str:
    digest = hashlib.sha256(f"{source_id}|{url}".encode("utf-8")).hexdigest()[:20]
    return f"ple-{digest}"


def _source_index(config: ProjectConfig) -> dict[str, dict[str, Any]]:
    return {
        source["source_id"]: source
        for game in config.player_live_sources
        for source in game["sources"]
    }


def _normalize_dcinside_evidence(
    config: ProjectConfig,
    report: dict[str, Any],
) -> list[dict[str, Any]]:
    sources = _source_index(config)
    evidence: list[dict[str, Any]] = []
    for post in report["posts"]:
        source = sources[post["source_id"]]
        url = post["url"]
        evidence.append(
            {
                "evidence_id": _evidence_id(post["source_id"], url),
                "game_id": post["game_id"],
                "source_id": post["source_id"],
                "platform": post["platform"],
                "source_type": post["source_type"],
                "evidence_role": source["evidence_role"],
                "classification": classification_for_role(source["evidence_role"]).value,
                "url": url,
                "source_host": urlparse(url).hostname or "",
                "title": post["title"],
                "published_at": post["published_at"],
                "collected_at": post["collected_at"],
                "normalized_text": post["normalized_text"],
                "content_hash": post["content_hash"],
                "content_availability": post["content_availability"],
                "comment_count": post["comment_count"],
                "view_count": post["view_count"],
                "recommendation_count": post["recommendation_count"],
                "previous_content_hash": post["previous_content_hash"],
                "change_type": post["change_type"],
            }
        )
    return evidence


def _deduplicate_gaps(gaps: list[dict[str, str]]) -> list[dict[str, str]]:
    unique: dict[tuple[str, str, str], dict[str, str]] = {}
    for gap in gaps:
        key = (gap["game_id"], gap["source"], gap["reason"])
        unique[key] = gap
    return list(unique.values())


def collect_player_live_evidence(
    config: ProjectConfig,
    state: StateStore,
    game_ids: tuple[str, ...],
    *,
    client: HttpClient | None = None,
    collected_at: datetime | None = None,
    max_listing_pages: int = 3,
    max_details_per_game: int = 20,
    detail_workers: int = 4,
) -> dict[str, Any]:
    """Collect active adapters and emit one provenance-preserving payload."""

    observed_at = collected_at or now_kst()
    dcinside = collect_dcinside_posts(
        config,
        state,
        game_ids,
        client=client,
        max_listing_pages=max_listing_pages,
        max_details_per_game=max_details_per_game,
        detail_workers=detail_workers,
        collected_at=observed_at,
    )
    youtube = collect_official_youtube_evidence(
        config,
        state,
        game_ids,
        client=client,
        collected_at=observed_at,
    )
    evidence = _normalize_dcinside_evidence(config, dcinside) + list(youtube["evidence"])
    evidence.sort(key=lambda item: item["published_at"], reverse=True)
    gaps = list(dcinside["coverage_gaps"]) + list(youtube["coverage_gaps"])

    source_coverage: list[dict[str, Any]] = []
    for game_id in game_ids:
        dc_metrics = dcinside["metrics"].get(game_id, {})
        yt_metrics = youtube["metrics"].get(game_id, {})
        dc_count = int(dc_metrics.get("detail_count", 0))
        yt_count = int(yt_metrics.get("item_count", 0))
        source_coverage.extend(
            (
                {
                    "game_id": game_id,
                    "adapter": "dcinside-html-v1",
                    "status": "EVIDENCE" if dc_count else "EMPTY_OR_GAP",
                    "item_count": dc_count,
                },
                {
                    "game_id": game_id,
                    "adapter": "official-youtube-rss-v1",
                    "status": (
                        "EVIDENCE"
                        if yt_count
                        else "EMPTY"
                        if yt_metrics.get("accessible")
                        else "GAP"
                    ),
                    "item_count": yt_count,
                },
            )
        )
        if dc_count + yt_count == 0:
            gaps.append(
                {
                    "game_id": game_id,
                    "source": "PLAYER_LIVE_ACTIVE_SOURCES",
                    "reason": "no accessible recent evidence from active Player Live adapters",
                }
            )

    classification_counts = {
        classification: sum(
            item["classification"] == classification for item in evidence
        )
        for classification in (
            "OFFICIAL_FACT",
            "PLAYER_CLAIM",
            "CREATOR_ANALYSIS",
            "UNKNOWN",
        )
    }
    return {
        "collected_at": observed_at,
        "game_scope": game_ids,
        "schema_version": 1,
        "evidence": evidence,
        "coverage_gaps": _deduplicate_gaps(gaps),
        "source_coverage": source_coverage,
        "classification_counts": classification_counts,
        "adapter_metrics": {
            "dcinside": dcinside["metrics"],
            "official_youtube": youtube["metrics"],
        },
    }
