"""Convert collected official notices into validated Signal objects."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any

from market_signal.models import CollectedNotice
from shared.json_utils import dumps
from shared.openai_client import OpenAIResponsesClient
from shared.schemas import (
    BMItemType,
    Evidence,
    PMMetricContext,
    RouteTarget,
    RoutingHint,
    Severity,
    Signal,
    SignalCategory,
    SourceType,
)


ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "event_key": {"type": "string", "minLength": 1},
        "title": {"type": "string", "minLength": 1},
        "summary": {"type": "string", "minLength": 1},
        "category": {"type": "string", "enum": [item.value for item in SignalCategory]},
        "severity": {"type": "string", "enum": [item.value for item in Severity]},
        "bm_item_types": {"type": "array", "items": {"type": "string", "enum": [item.value for item in BMItemType]}},
        "pm_terms": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [
                    "DAU", "NRU", "Gross", "Sales", "Net gross", "Net sales", "PU", "BU", "NPU", "MPU",
                    "PUR", "BUR", "MPUR", "ARPPU", "ARPDAU", "Retention", "Organic", "Non organic", "CU",
                    "MCU", "UV", "TS", "KPI", "LTV", "PLC", "BEP", "ROI", "CAC", "CRC", "RS", "LF", "MG", "MOU",
                ],
            },
        },
        "pm_rationale": {"type": "string"},
        "severity_reason": {"type": "string", "minLength": 1},
    },
    "required": ["event_key", "title", "summary", "category", "severity", "bm_item_types", "pm_terms", "pm_rationale", "severity_reason"],
}


INSTRUCTIONS = """You are the Market Signal Scout for Korean live-service games.
Analyze only the supplied official notice. Do not infer player sentiment, KPI values,
revenue impact, or facts absent from the notice. Choose only allowed enum values.
Use PM terms only when an internal metric check is plausibly relevant; otherwise use
an empty list. event_key must be a short stable lowercase ASCII slug describing the
underlying event, suitable for merging multiple official evidence items."""


def analyze_notices(client: OpenAIResponsesClient, notices: tuple[CollectedNotice, ...]) -> tuple[Signal, ...]:
    grouped: dict[tuple[str, str], list[tuple[CollectedNotice, dict[str, Any]]]] = defaultdict(list)
    for notice in notices:
        payload = {
            "game_id": notice.game_id,
            "title": notice.title,
            "published_at": notice.published_at,
            "official_text": notice.normalized_text[:20_000],
        }
        result = client.structured(
            instructions=INSTRUCTIONS,
            input_text=dumps(payload),
            name="market_signal_analysis",
            schema=ANALYSIS_SCHEMA,
        )
        grouped[(notice.game_id, result["event_key"])].append((notice, result))

    signals: list[Signal] = []
    for (game_id, event_key), items in grouped.items():
        first_result = items[0][1]
        category = SignalCategory(first_result["category"])
        bm_types = tuple(BMItemType(item) for item in first_result["bm_item_types"])
        if category is not SignalCategory.BM:
            bm_types = ()
        severity = max((Severity(item[1]["severity"]) for item in items), key=lambda value: list(Severity).index(value))
        evidence = tuple(
            Evidence(
                evidence_id="ev-" + hashlib.sha256(notice.url.encode("utf-8")).hexdigest()[:16],
                source_type=SourceType(notice.source_type),
                url=notice.url,
                title=notice.title,
                published_at=notice.published_at,
                collected_at=notice.collected_at,
                content_hash=notice.content_hash,
                modified_at=notice.collected_at if notice.change_type == "MODIFIED" else None,
                previous_content_hash=notice.previous_content_hash,
            )
            for notice, _ in items
        )
        should_route = severity in {Severity.HIGH, Severity.CRITICAL}
        signals.append(
            Signal(
                signal_id="sig-" + hashlib.sha256(f"{game_id}:{event_key}".encode("utf-8")).hexdigest()[:16],
                event_key=event_key,
                game_id=game_id,
                title=first_result["title"],
                summary=first_result["summary"],
                category=category,
                severity=severity,
                observed_at=max(notice.published_at for notice, _ in items),
                evidence=evidence,
                pm_metric_context=PMMetricContext(
                    terms=tuple(first_result["pm_terms"]),
                    rationale=first_result["pm_rationale"],
                    verification_needed=bool(first_result["pm_terms"]),
                ),
                bm_item_types=bm_types,
                routing=RoutingHint(
                    target=RouteTarget.PLAYER_LIVE_WATCH if should_route else RouteTarget.NONE,
                    deep_dive_required=should_route,
                    reason=first_result["severity_reason"],
                ),
            )
        )
    return tuple(signals)
