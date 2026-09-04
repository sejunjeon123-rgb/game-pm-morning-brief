"""Load and validate tracked runtime configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ProjectConfig:
    root: Path
    runtime: dict[str, Any]
    games: tuple[dict[str, Any], ...]
    sources: tuple[dict[str, Any], ...]
    source_policy: dict[str, Any]
    player_live_sources: tuple[dict[str, Any], ...] = ()

    @property
    def game_ids(self) -> tuple[str, ...]:
        return tuple(item["id"] for item in self.games)


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def load_project_config(root: Path) -> ProjectConfig:
    runtime = _read_json(root / "config" / "runtime.json")
    daily = runtime.get("daily", {})
    if daily.get("engine") != "compact-v1" or daily.get("api_retries") != 0:
        raise ValueError("daily engine requires compact-v1 without paid retries")
    bounds = {"max_official_details_per_game": 8, "max_player_details_per_game": 5,
              "max_listing_pages": 2, "max_documents_per_game": 13,
              "max_text_characters": 1800, "max_output_tokens": 2500,
              "http_timeout_seconds": 10, "api_timeout_seconds": 60,
              "official_http_timeout_seconds": 20, "official_http_retries": 1}
    if any(type(daily.get(k)) is not int or not 0 < daily[k] <= limit for k, limit in bounds.items()):
        raise ValueError("daily collection or API bounds exceed the compact budget")
    games_doc = _read_json(root / "config" / "games.json")
    sources_doc = _read_json(root / "config" / "sources.json")
    player_live_doc = _read_json(root / "config" / "player_live_sources.json")
    games = tuple(games_doc.get("games", ()))
    sources = tuple(sources_doc.get("sources", ()))
    source_policy = sources_doc.get("source_policy", {})
    player_live_sources = tuple(player_live_doc.get("games", ()))
    game_ids = [item["id"] for item in games]
    source_ids = [item["game_id"] for item in sources]
    if len(games) != 8 or len(game_ids) != len(set(game_ids)):
        raise ValueError("games.json must contain eight unique core games")
    if set(game_ids) != set(source_ids):
        raise ValueError("every core game must have exactly one source entry")
    if source_policy.get("priority") != ["OFFICIAL_HOMEPAGE", "OFFICIAL_COMMUNITY", "OFFICIAL_YOUTUBE"]:
        raise ValueError("official source priority does not match the project contract")
    if source_policy.get("on_source_unavailable") != "CONTINUE_LOWER_PRIORITY":
        raise ValueError("unavailable official sources must fall through to the next configured priority")
    if source_policy.get("on_all_sources_empty") != "REPORT_COVERAGE_GAP":
        raise ValueError("empty official-source results must be reported as a coverage gap")
    if source_policy.get("external_relay_allowed") is not False:
        raise ValueError("external source relays are disabled by project policy")
    if runtime.get("timezone") != "Asia/Seoul":
        raise ValueError("runtime timezone must be Asia/Seoul")
    radar = runtime.get("game_radar", {})
    if radar.get("max_games_per_run") != 3 or radar.get("min_independent_sources") != 2:
        raise ValueError("Game Radar policy does not match the root contract")
    player_live = runtime.get("player_live", {})
    if player_live.get("evidence_priority") != [
        "OFFICIAL_HOMEPAGE",
        "OFFICIAL_COMMUNITY",
        "OFFICIAL_YOUTUBE",
        "PUBLIC_COMMUNITY",
        "PUBLIC_CREATOR_YOUTUBE",
        "PUBLIC_LIVE_PLATFORM",
    ]:
        raise ValueError("Player Live evidence priority does not match the project contract")
    if player_live.get("public_creator_youtube_classification") != "PLAYER_CLAIM_OR_CREATOR_ANALYSIS":
        raise ValueError("public creator YouTube evidence must remain a claim or creator analysis")
    player_live_ids = [item.get("game_id") for item in player_live_sources]
    if len(player_live_sources) != 8 or len(player_live_ids) != len(set(player_live_ids)):
        raise ValueError("player_live_sources.json must contain eight unique core games")
    if set(player_live_ids) != set(game_ids):
        raise ValueError("every core game must have one Player Live source entry")
    approved_platforms = set(player_live.get("approved_platforms", ()))
    official_youtube_by_game = {item["game_id"]: item.get("youtube") for item in sources}
    seen_source_ids: set[str] = set()
    for game_entry in player_live_sources:
        game_sources = game_entry.get("sources", ())
        if not game_sources:
            raise ValueError(f"Player Live source list is empty: {game_entry.get('game_id')}")
        for source in game_sources:
            source_id = source.get("source_id", "")
            if not source_id or source_id in seen_source_ids:
                raise ValueError(f"Player Live source_id must be unique: {source_id}")
            seen_source_ids.add(source_id)
            if source.get("platform") not in approved_platforms:
                raise ValueError(f"unapproved Player Live platform: {source.get('platform')}")
            if source.get("source_type") not in {
                "OFFICIAL_COMMUNITY",
                "OFFICIAL_YOUTUBE",
                "PUBLIC_COMMUNITY",
                "PUBLIC_CREATOR_YOUTUBE",
                "PUBLIC_LIVE_PLATFORM",
            }:
                raise ValueError(f"invalid Player Live source type: {source.get('source_type')}")
            if source.get("status") != "VERIFIED":
                raise ValueError(f"only verified Player Live sources may be configured: {source_id}")
            if source.get("collection_status") not in {"RSS_READY", "ADAPTER_READY", "ADAPTER_PENDING"}:
                raise ValueError(f"invalid Player Live collection status: {source_id}")
            if source.get("evidence_role") not in {
                "OFFICIAL_FACT",
                "OFFICIAL_COMMUNITY_REACTION",
                "PLAYER_REACTION",
                "CREATOR_ANALYSIS",
            }:
                raise ValueError(f"invalid Player Live evidence role: {source_id}")
            url = source.get("url", "")
            if not isinstance(url, str) or not url.startswith("https://"):
                raise ValueError(f"Player Live source URL must be absolute HTTPS: {source_id}")
            if source.get("source_type") == "OFFICIAL_YOUTUBE" and url != official_youtube_by_game[game_entry["game_id"]]:
                raise ValueError(f"official YouTube source mismatch: {source_id}")
    return ProjectConfig(
        root=root,
        runtime=runtime,
        games=games,
        sources=sources,
        source_policy=source_policy,
        player_live_sources=player_live_sources,
    )
