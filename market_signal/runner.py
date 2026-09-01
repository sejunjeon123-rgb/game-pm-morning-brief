"""Market Signal V1 orchestration for collection and optional OpenAI analysis."""

from __future__ import annotations

import os
import json
from dataclasses import asdict
from pathlib import Path
from datetime import datetime
from typing import Any

from app.config import ProjectConfig
from market_signal.analyzer import analyze_notices_with_report
from market_signal.collector import collect_official_notices
from market_signal.models import CollectedNotice
from market_signal.youtube_collector import collect_official_youtube
from shared.openai_client import OpenAIResponsesClient
from shared.state_store import StateStore
from shared.time_utils import parse_iso_kst


def run_market_signal(
    config: ProjectConfig,
    state: StateStore,
    game_ids: tuple[str, ...],
    *,
    analyze: bool = False,
) -> dict[str, Any]:
    notice_report = collect_official_notices(config, state, game_ids)
    youtube_report = collect_official_youtube(config, state, game_ids)
    report = {
        "collected_at": notice_report["collected_at"],
        "game_scope": game_ids,
        "notices": notice_report["notices"],
        "videos": youtube_report["videos"],
        "coverage_gaps": notice_report["coverage_gaps"] + youtube_report["coverage_gaps"],
    }
    report["signals"] = []
    report["analysis_status"] = "not_requested"
    if not analyze:
        return report
    api_key = os.environ.get("OPENAI_API_KEY", "")
    model = os.environ.get("OPENAI_MODEL", "")
    if not api_key or not model:
        report["analysis_status"] = "blocked_missing_openai_configuration"
        return report
    notices = _notices_from_items(report["notices"] + report["videos"])
    outcome = analyze_notices_with_report(OpenAIResponsesClient(api_key, model), notices, state=state)
    report["signals"] = [asdict(item) for item in outcome.signals]
    report["excluded_inputs"] = list(outcome.excluded_inputs)
    report["analysis_metrics"] = outcome.metrics
    report["analysis_status"] = "completed"
    return report


def analyze_collection_file(path: Path, state: StateStore | None = None) -> dict[str, Any]:
    """Analyze a saved collection without recollecting or mutating source state."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("collection file must contain a JSON object")
    items = raw.get("notices", []) + raw.get("videos", [])
    if not items:
        raise ValueError("collection file contains no notices or videos")
    api_key = os.environ.get("OPENAI_API_KEY", "")
    model = os.environ.get("OPENAI_MODEL", "")
    if not api_key or not model:
        return {
            "analysis_status": "blocked_missing_openai_configuration",
            "input_file": str(path),
            "input_count": len(items),
            "signals": [],
        }
    notices = _notices_from_items(items)
    outcome = analyze_notices_with_report(OpenAIResponsesClient(api_key, model), notices, state=state)
    return {
        "analysis_status": "completed",
        "input_file": str(path),
        "input_count": len(items),
        "signal_count": len(outcome.signals),
        "excluded_inputs": list(outcome.excluded_inputs),
        "analysis_metrics": outcome.metrics,
        "signals": [asdict(item) for item in outcome.signals],
    }


def _notices_from_items(items: list[dict[str, Any]]) -> tuple[CollectedNotice, ...]:
    return tuple(
        CollectedNotice(
            game_id=item["game_id"],
            url=item["url"],
            title=item["title"],
            published_at=_parse_timestamp(item["published_at"]),
            collected_at=_parse_timestamp(item["collected_at"]),
            normalized_text=item["normalized_text"],
            content_hash=item["content_hash"],
            previous_content_hash=item.get("previous_content_hash"),
            source_type=item.get("source_type", "OFFICIAL_NOTICE"),
        )
        for item in items
    )


def _parse_timestamp(value: object) -> datetime:
    return parse_iso_kst(value.isoformat() if isinstance(value, datetime) else str(value))
