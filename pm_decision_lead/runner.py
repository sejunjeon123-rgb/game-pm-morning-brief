"""File-based PM Decision Lead orchestration."""

from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
from typing import Any

from pm_decision_lead.analyzer import synthesize_morning_brief
from shared.openai_client import OpenAIResponsesClient


def build_morning_brief_from_files(
    market_signal_file: Path,
    player_live_file: Path,
    *,
    game_scope: tuple[str, ...],
) -> dict[str, Any]:
    market = _read_report(market_signal_file, "Market Signal")
    player = _read_report(player_live_file, "Player Live")
    if not str(market.get("analysis_status", "")).startswith("completed"):
        return {"decision_status": "blocked_market_signal_analysis", "decisions": []}
    if not str(player.get("analysis_status", "")).startswith("completed"):
        return {"decision_status": "blocked_player_live_analysis", "decisions": []}
    api_key = os.environ.get("OPENAI_API_KEY", "")
    model = os.environ.get("OPENAI_MODEL", "")
    if not api_key or not model:
        return {"decision_status": "blocked_missing_openai_configuration", "decisions": []}
    gaps = tuple(
        item for item in market.get("coverage_gaps", []) + player.get("coverage_gaps", [])
        if isinstance(item, dict)
    )
    try:
        brief = synthesize_morning_brief(
            OpenAIResponsesClient(api_key, model),
            game_scope=game_scope,
            signals=tuple(item for item in market.get("signals", []) if isinstance(item, dict)),
            insights=tuple(item for item in player.get("insights", []) if isinstance(item, dict)),
            coverage_gaps=gaps,
        )
    except ValueError as exc:
        return {
            "decision_status": "blocked_validation",
            "reason": str(exc),
            "decisions": [],
        }
    return {"decision_status": "completed", "brief": asdict(brief)}


def _read_report(path: Path, label: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} report must contain a JSON object")
    return value
