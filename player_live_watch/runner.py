"""Saved Player Live collection analysis orchestration."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any, Mapping

from player_live_watch.analyzer import analyze_player_evidence
from player_live_watch.models import CollectedPlayerEvidence, EvidenceClassification
from shared.openai_client import OpenAIResponsesClient
from shared.state_store import StateStore
from shared.time_utils import parse_iso_kst


def analyze_player_live_collection_file(
    path: Path,
    *,
    state: StateStore | None = None,
    signal_file: Path | None = None,
) -> dict[str, Any]:
    """Analyze a saved common Evidence payload without recollecting sources."""

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Player Live collection file must contain a JSON object")
    raw_evidence = raw.get("evidence", [])
    if not isinstance(raw_evidence, list):
        raise ValueError("Player Live collection evidence must be an array")
    if not raw_evidence:
        return {
            "analysis_status": "completed_no_evidence",
            "input_file": str(path),
            "input_count": 0,
            "insight_count": 0,
            "coverage_gaps": raw.get("coverage_gaps", []),
            "insights": [],
        }

    source_signals = _load_signal_context(signal_file)
    api_key = os.environ.get("OPENAI_API_KEY", "")
    model = os.environ.get("OPENAI_MODEL", "")
    if not api_key or not model:
        return {
            "analysis_status": "blocked_missing_openai_configuration",
            "input_file": str(path),
            "input_count": len(raw_evidence),
            "insights": [],
        }
    evidence = _evidence_from_items(raw_evidence)
    outcome = analyze_player_evidence(
        OpenAIResponsesClient(api_key, model),
        evidence,
        source_signals=source_signals,
        state=state,
    )
    return {
        "analysis_status": "completed",
        "input_file": str(path),
        "input_count": len(evidence),
        "insight_count": len(outcome.insights),
        "excluded_inputs": list(outcome.excluded_inputs),
        "analysis_metrics": outcome.metrics,
        "coverage_gaps": raw.get("coverage_gaps", []),
        "insights": [asdict(item) for item in outcome.insights],
    }


def _load_signal_context(path: Path | None) -> tuple[Mapping[str, Any], ...]:
    if path is None or not path.exists():
        return ()
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Market Signal file must contain a JSON object")
    signals = value.get("signals", [])
    if not isinstance(signals, list):
        raise ValueError("Market Signal file signals must be an array")
    return tuple(item for item in signals if isinstance(item, Mapping))


def _evidence_from_items(
    items: list[dict[str, Any]],
) -> tuple[CollectedPlayerEvidence, ...]:
    return tuple(
        CollectedPlayerEvidence(
            evidence_id=str(item["evidence_id"]),
            game_id=str(item["game_id"]),
            source_id=str(item["source_id"]),
            platform=str(item["platform"]),
            source_type=str(item["source_type"]),
            evidence_role=str(item["evidence_role"]),
            classification=EvidenceClassification(item["classification"]),
            url=str(item["url"]),
            source_host=str(item["source_host"]),
            title=str(item["title"]),
            published_at=_parse_timestamp(item["published_at"]),
            collected_at=_parse_timestamp(item["collected_at"]),
            normalized_text=str(item["normalized_text"]),
            content_hash=str(item["content_hash"]),
            content_availability=str(item["content_availability"]),
            comment_count=_optional_int(item.get("comment_count")),
            view_count=_optional_int(item.get("view_count")),
            recommendation_count=_optional_int(item.get("recommendation_count")),
            previous_content_hash=(
                str(item["previous_content_hash"])
                if item.get("previous_content_hash")
                else None
            ),
        )
        for item in items
    )


def _parse_timestamp(value: object) -> datetime:
    return parse_iso_kst(value.isoformat() if isinstance(value, datetime) else str(value))


def _optional_int(value: object) -> int | None:
    return int(value) if value is not None else None
