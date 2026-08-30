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
    games_doc = _read_json(root / "config" / "games.json")
    sources_doc = _read_json(root / "config" / "sources.json")
    games = tuple(games_doc.get("games", ()))
    sources = tuple(sources_doc.get("sources", ()))
    source_policy = sources_doc.get("source_policy", {})
    game_ids = [item["id"] for item in games]
    source_ids = [item["game_id"] for item in sources]
    if len(games) != 8 or len(game_ids) != len(set(game_ids)):
        raise ValueError("games.json must contain eight unique core games")
    if set(game_ids) != set(source_ids):
        raise ValueError("every core game must have exactly one source entry")
    if source_policy.get("priority") != ["OFFICIAL_HOMEPAGE", "OFFICIAL_COMMUNITY", "OFFICIAL_YOUTUBE"]:
        raise ValueError("official source priority does not match the project contract")
    if runtime.get("timezone") != "Asia/Seoul":
        raise ValueError("runtime timezone must be Asia/Seoul")
    radar = runtime.get("game_radar", {})
    if radar.get("max_games_per_run") != 3 or radar.get("min_independent_sources") != 2:
        raise ValueError("Game Radar policy does not match the root contract")
    return ProjectConfig(root=root, runtime=runtime, games=games, sources=sources, source_policy=source_policy)
