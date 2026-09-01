"""Convert collected official documents into validated, merged Signal objects."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Any, Iterable, Mapping

from market_signal.models import CollectedNotice
from shared.json_utils import dumps
from shared.openai_client import OpenAIResponsesClient
from shared.pm_metrics import PM_TERM_DEFINITIONS, is_korean_prose, sanitize_pm_metric_context
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
from shared.state_store import StateStore
from shared.time_utils import parse_iso_kst


ANALYZER_VERSION = "market-signal-batch-v3"
MAX_DOCUMENTS_PER_BATCH = 6
MAX_BATCH_CHARACTERS = 50_000
MAX_PARALLEL_REQUESTS = 3
MAX_DOCUMENT_CHARACTERS = 20_000
_EVENT_KEY = re.compile(r"^[a-z0-9][a-z0-9-]{0,127}$")
_SOURCE_PRIORITY = {
    SourceType.OFFICIAL_HOMEPAGE: 0,
    SourceType.OFFICIAL_NOTICE: 0,
    SourceType.OFFICIAL_COMMUNITY: 1,
    SourceType.OFFICIAL_YOUTUBE: 2,
}
_SEVERITY_PRIORITY = {value: index for index, value in enumerate(Severity)}


EVENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "event_key": {"type": "string", "minLength": 1, "pattern": "^[a-z0-9][a-z0-9-]{0,127}$"},
        "input_ids": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}},
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
        "source_conflicts": {"type": "array", "items": {"type": "string", "minLength": 1}},
    },
    "required": [
        "event_key", "input_ids", "title", "summary", "category", "severity", "bm_item_types",
        "pm_terms", "pm_rationale", "severity_reason", "source_conflicts",
    ],
}


ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "events": {"type": "array", "items": EVENT_SCHEMA},
        "excluded_inputs": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "input_id": {"type": "string", "minLength": 1},
                    "reason": {"type": "string", "minLength": 1},
                },
                "required": ["input_id", "reason"],
            },
        },
    },
    "required": ["events", "excluded_inputs"],
}


INSTRUCTIONS = """You are the Market Signal Scout for Korean live-service games.
Analyze all supplied official documents for exactly one game. Cluster documents that
describe the same underlying event into one event and list every supporting input_id.
Do not merge events merely because their dates or keywords overlap. Do not infer player
sentiment, KPI values, revenue impact, or facts absent from the documents. Choose only
allowed enum values. Use PM terms only when an internal metric check is plausibly
relevant; otherwise use an empty list. event_key must be a stable lowercase ASCII slug.
Record material differences between official sources in source_conflicts. Every supplied
input_id must appear exactly once, either in one event or in excluded_inputs. Exclude an
input only when it is not a discrete market signal, and state the factual reason. Before
returning, re-scan the input list for completeness.

Write title, summary, pm_rationale, severity_reason, source_conflicts, and exclusion
reasons in Korean. Proper nouns and approved acronyms may remain in their original
form, but the explanatory prose must be Korean.

The canonical PM meanings are: """ + "; ".join(
    f"{term}={definition}" for term, definition in PM_TERM_DEFINITIONS.items()
) + """. Parenthetical benchmarks, fixed fee percentages, and personal rules of thumb
are not definitions and must not be assumed. PU means paying users, never pick-up. CU
means concurrent users, never content usage. Include a PM term only when pm_rationale
states in Korean which internal metric should be checked or compared. Never state that
an unavailable KPI increased, decreased, improved, or worsened."""


@dataclass(frozen=True, slots=True)
class AnalysisOutcome:
    signals: tuple[Signal, ...]
    excluded_inputs: tuple[dict[str, str], ...]
    metrics: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _Batch:
    index: int
    game_id: str
    documents: tuple[tuple[str, CollectedNotice], ...]


@dataclass(frozen=True, slots=True)
class _AnalyzedEvent:
    game_id: str
    result: Mapping[str, Any]
    documents: tuple[CollectedNotice, ...]


def analyze_notices(client: OpenAIResponsesClient, notices: tuple[CollectedNotice, ...]) -> tuple[Signal, ...]:
    """Compatibility wrapper returning Signals while using batch analysis."""
    return analyze_notices_with_report(client, notices).signals


def analyze_notices_with_report(
    client: OpenAIResponsesClient,
    notices: tuple[CollectedNotice, ...],
    *,
    state: StateStore | None = None,
) -> AnalysisOutcome:
    started = perf_counter()
    grouped = _group_by_game(notices)
    cache = state.read("market-signal/analysis_cache", {"version": ANALYZER_VERSION, "games": {}}) if state else {}
    cache_games = dict(cache.get("games", {})) if cache.get("version") == ANALYZER_VERSION else {}
    cached_signals: list[Signal] = []
    cached_exclusions: list[dict[str, str]] = []
    pending: dict[str, tuple[CollectedNotice, ...]] = {}
    cache_hits: list[str] = []

    for game_id, game_notices in grouped.items():
        fingerprint = _game_fingerprint(client, game_notices)
        entry = cache_games.get(game_id, {})
        if entry.get("fingerprint") == fingerprint:
            try:
                cached_signals.extend(_signal_from_dict(value) for value in entry.get("signals", []))
                cached_exclusions.extend(_validate_cached_exclusions(entry.get("excluded_inputs", [])))
                cache_hits.append(game_id)
                continue
            except (KeyError, TypeError, ValueError):
                pass
        pending[game_id] = game_notices

    batches = _build_batches(pending)
    batch_results = _run_batches(client, batches)
    analyzed_events: list[_AnalyzedEvent] = []
    analyzed_exclusions: list[dict[str, str]] = []
    for batch in batches:
        events, exclusions = _validate_batch_result(batch, batch_results[batch.index])
        analyzed_events.extend(events)
        analyzed_exclusions.extend(exclusions)

    fresh_signals = _merge_events(analyzed_events)
    all_signals = tuple(sorted((*cached_signals, *fresh_signals), key=lambda item: (item.game_id, item.observed_at, item.signal_id)))
    all_exclusions = tuple((*cached_exclusions, *analyzed_exclusions))

    if state:
        for game_id, game_notices in pending.items():
            game_input_ids = {_input_id(item) for item in game_notices}
            cache_games[game_id] = {
                "fingerprint": _game_fingerprint(client, game_notices),
                "signals": [asdict(item) for item in fresh_signals if item.game_id == game_id],
                "excluded_inputs": [item for item in analyzed_exclusions if item["input_id"] in game_input_ids],
            }
        state.write("market-signal/analysis_cache", {"version": ANALYZER_VERSION, "games": cache_games})

    metrics = {
        "analyzer_version": ANALYZER_VERSION,
        "input_count": len(notices),
        "game_count": len(grouped),
        "batch_count": len(batches),
        "api_call_count": len(batches),
        "cache_hit_games": sorted(cache_hits),
        "analyzed_games": sorted(pending),
        "max_parallel_requests": min(MAX_PARALLEL_REQUESTS, len(batches)),
        "elapsed_seconds": round(perf_counter() - started, 3),
    }
    return AnalysisOutcome(all_signals, all_exclusions, metrics)


def _group_by_game(notices: Iterable[CollectedNotice]) -> dict[str, tuple[CollectedNotice, ...]]:
    grouped: dict[str, list[CollectedNotice]] = defaultdict(list)
    for notice in notices:
        grouped[notice.game_id].append(notice)
    return {
        game_id: tuple(sorted(values, key=lambda item: (item.published_at, item.url), reverse=True))
        for game_id, values in sorted(grouped.items())
    }


def _input_id(notice: CollectedNotice) -> str:
    raw = f"{notice.game_id}|{notice.url}|{notice.title}|{notice.content_hash}"
    return "doc-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _document_payload(input_id: str, notice: CollectedNotice) -> dict[str, Any]:
    return {
        "input_id": input_id,
        "source_type": notice.source_type,
        "url": notice.url,
        "title": notice.title,
        "published_at": notice.published_at.isoformat(),
        "change_type": notice.change_type,
        "official_text": notice.normalized_text[:MAX_DOCUMENT_CHARACTERS],
    }


def _build_batches(grouped: Mapping[str, tuple[CollectedNotice, ...]]) -> tuple[_Batch, ...]:
    batches: list[_Batch] = []
    for game_id, notices in grouped.items():
        current: list[tuple[str, CollectedNotice]] = []
        current_size = 0
        for notice in notices:
            input_id = _input_id(notice)
            size = len(dumps(_document_payload(input_id, notice), indent=None))
            if current and (len(current) >= MAX_DOCUMENTS_PER_BATCH or current_size + size > MAX_BATCH_CHARACTERS):
                batches.append(_Batch(len(batches), game_id, tuple(current)))
                current, current_size = [], 0
            current.append((input_id, notice))
            current_size += size
        if current:
            batches.append(_Batch(len(batches), game_id, tuple(current)))
    return tuple(batches)


def _run_batches(client: OpenAIResponsesClient, batches: tuple[_Batch, ...]) -> dict[int, dict[str, Any]]:
    if not batches:
        return {}

    def run(batch: _Batch) -> dict[str, Any]:
        payload = {
            "game_id": batch.game_id,
            "documents": [_document_payload(input_id, notice) for input_id, notice in batch.documents],
        }
        return client.structured(
            instructions=INSTRUCTIONS,
            input_text=dumps(payload, indent=None),
            name="market_signal_game_batch",
            schema=ANALYSIS_SCHEMA,
        )

    results: dict[int, dict[str, Any]] = {}
    workers = min(MAX_PARALLEL_REQUESTS, len(batches))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="market-signal") as executor:
        futures = {executor.submit(run, batch): batch.index for batch in batches}
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    return results


def _validate_batch_result(batch: _Batch, result: Mapping[str, Any]) -> tuple[list[_AnalyzedEvent], list[dict[str, str]]]:
    expected = {input_id for input_id, _ in batch.documents}
    notice_by_id = dict(batch.documents)
    assigned: list[str] = []
    events: list[_AnalyzedEvent] = []
    seen_event_keys: set[str] = set()
    for event in result.get("events", []):
        if not isinstance(event, Mapping):
            raise ValueError("batch event must be an object")
        event_key = _normalize_event_key(str(event.get("event_key", "")))
        if not _EVENT_KEY.fullmatch(event_key):
            raise ValueError(f"invalid event_key: {event_key!r}")
        if event_key in seen_event_keys:
            raise ValueError(f"duplicate event_key within batch: {event_key}")
        seen_event_keys.add(event_key)
        for field in ("title", "summary", "severity_reason"):
            if not is_korean_prose(str(event.get(field, ""))):
                raise ValueError(f"analysis {field} must be Korean prose")
        pm_terms = tuple(str(value) for value in event.get("pm_terms", []))
        if pm_terms and not is_korean_prose(str(event.get("pm_rationale", ""))):
            raise ValueError("analysis pm_rationale must be Korean prose when PM terms are present")
        for conflict in event.get("source_conflicts", []):
            if not is_korean_prose(str(conflict)):
                raise ValueError("analysis source_conflicts must be Korean prose")
        input_ids = [str(value) for value in event.get("input_ids", [])]
        if not input_ids:
            raise ValueError("batch event requires input_ids")
        assigned.extend(input_ids)
        normalized_event = dict(event)
        normalized_event["event_key"] = event_key
        events.append(_AnalyzedEvent(batch.game_id, normalized_event, tuple(notice_by_id[value] for value in input_ids if value in notice_by_id)))

    exclusions: list[dict[str, str]] = []
    for item in result.get("excluded_inputs", []):
        if not isinstance(item, Mapping):
            raise ValueError("excluded input must be an object")
        input_id, reason = str(item.get("input_id", "")), str(item.get("reason", "")).strip()
        if not reason:
            raise ValueError("excluded input requires a reason")
        if not is_korean_prose(reason):
            raise ValueError("excluded input reason must be Korean prose")
        assigned.append(input_id)
        exclusions.append({"input_id": input_id, "game_id": batch.game_id, "reason": reason})

    assigned_set = set(assigned)
    duplicates = sorted({value for value in assigned if assigned.count(value) > 1})
    if duplicates or assigned_set != expected:
        missing = sorted(expected - assigned_set)
        unknown = sorted(assigned_set - expected)
        raise ValueError(f"analysis completeness gate failed: missing={missing}, unknown={unknown}, duplicates={duplicates}")
    if any(not event.documents for event in events):
        raise ValueError("analysis event referenced no known input documents")
    return events, exclusions


def _merge_events(events: Iterable[_AnalyzedEvent]) -> tuple[Signal, ...]:
    grouped: dict[tuple[str, str], list[_AnalyzedEvent]] = defaultdict(list)
    for event in events:
        grouped[(event.game_id, str(event.result["event_key"]))].append(event)

    signals: list[Signal] = []
    for (game_id, event_key), items in grouped.items():
        representative = min(items, key=_representative_rank)
        result = representative.result
        category = SignalCategory(result["category"])
        severity = max((Severity(item.result["severity"]) for item in items), key=_SEVERITY_PRIORITY.__getitem__)
        documents = _unique_documents(document for item in items for document in item.documents)
        evidence = tuple(_evidence(document) for document in sorted(documents, key=_document_rank))
        raw_pm_terms = _ordered_unique(str(term) for item in items for term in item.result["pm_terms"])
        pm_rationales = _ordered_unique(str(item.result["pm_rationale"]).strip() for item in items if str(item.result["pm_rationale"]).strip())
        pm_terms, pm_rationale = sanitize_pm_metric_context(raw_pm_terms, " / ".join(pm_rationales))
        bm_types = _ordered_unique(str(value) for item in items for value in item.result["bm_item_types"])
        if category is not SignalCategory.BM:
            bm_types = ()
        conflicts = _ordered_unique(str(value).strip() for item in items for value in item.result["source_conflicts"] if str(value).strip())
        severity_reason = next(
            str(item.result["severity_reason"])
            for item in items
            if Severity(item.result["severity"]) is severity
        )
        should_route = severity in {Severity.HIGH, Severity.CRITICAL}
        signals.append(
            Signal(
                signal_id="sig-" + hashlib.sha256(f"{game_id}:{event_key}".encode("utf-8")).hexdigest()[:16],
                event_key=event_key,
                game_id=game_id,
                title=str(result["title"]),
                summary=str(result["summary"]),
                category=category,
                severity=severity,
                observed_at=max(document.published_at for document in documents),
                evidence=evidence,
                source_conflicts=conflicts,
                pm_metric_context=PMMetricContext(
                    terms=pm_terms,
                    rationale=pm_rationale,
                    verification_needed=bool(pm_terms),
                ),
                bm_item_types=tuple(BMItemType(value) for value in bm_types),
                routing=RoutingHint(
                    target=RouteTarget.PLAYER_LIVE_WATCH if should_route else RouteTarget.NONE,
                    deep_dive_required=should_route,
                    reason=severity_reason,
                ),
            )
        )
    return tuple(signals)


def _representative_rank(event: _AnalyzedEvent) -> tuple[int, float]:
    source_rank = min(_SOURCE_PRIORITY.get(SourceType(item.source_type), 99) for item in event.documents)
    latest = max(item.published_at.timestamp() for item in event.documents)
    return source_rank, -latest


def _document_rank(notice: CollectedNotice) -> tuple[int, float, str]:
    return _SOURCE_PRIORITY.get(SourceType(notice.source_type), 99), -notice.published_at.timestamp(), notice.url


def _unique_documents(documents: Iterable[CollectedNotice]) -> tuple[CollectedNotice, ...]:
    values: dict[str, CollectedNotice] = {}
    for document in documents:
        values[_input_id(document)] = document
    return tuple(values.values())


def _ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def _normalize_event_key(value: str) -> str:
    normalized = re.sub(r"[_\s]+", "-", value.strip().lower())
    normalized = re.sub(r"[^a-z0-9-]+", "-", normalized)
    return re.sub(r"-+", "-", normalized).strip("-")[:128].rstrip("-")


def _evidence(notice: CollectedNotice) -> Evidence:
    return Evidence(
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


def _game_fingerprint(client: OpenAIResponsesClient, notices: tuple[CollectedNotice, ...]) -> str:
    model = str(getattr(client, "model", type(client).__name__))
    raw = "|".join((ANALYZER_VERSION, model, *sorted(_input_id(item) for item in notices)))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _signal_from_dict(value: Mapping[str, Any]) -> Signal:
    context = value.get("pm_metric_context", {})
    routing = value.get("routing", {})
    return Signal(
        signal_id=str(value["signal_id"]),
        event_key=str(value["event_key"]),
        game_id=str(value["game_id"]),
        title=str(value["title"]),
        summary=str(value["summary"]),
        category=SignalCategory(value["category"]),
        severity=Severity(value["severity"]),
        observed_at=parse_iso_kst(str(value["observed_at"])),
        evidence=tuple(
            Evidence(
                evidence_id=str(item["evidence_id"]),
                source_type=SourceType(item["source_type"]),
                url=str(item["url"]),
                title=str(item["title"]),
                published_at=parse_iso_kst(str(item["published_at"])),
                collected_at=parse_iso_kst(str(item["collected_at"])),
                content_hash=str(item["content_hash"]),
                modified_at=parse_iso_kst(str(item["modified_at"])) if item.get("modified_at") else None,
                previous_content_hash=item.get("previous_content_hash"),
            )
            for item in value["evidence"]
        ),
        source_conflicts=tuple(str(item) for item in value.get("source_conflicts", [])),
        pm_metric_context=PMMetricContext(
            terms=tuple(str(item) for item in context.get("terms", [])),
            rationale=str(context.get("rationale", "")),
            verification_needed=bool(context.get("verification_needed", False)),
        ),
        bm_item_types=tuple(BMItemType(item) for item in value.get("bm_item_types", [])),
        routing=RoutingHint(
            target=RouteTarget(routing.get("target", "NONE")),
            deep_dive_required=bool(routing.get("deep_dive_required", False)),
            reason=str(routing.get("reason", "")),
            final_router=str(routing.get("final_router", "pm-decision-lead")),
        ),
    )


def _validate_cached_exclusions(values: object) -> list[dict[str, str]]:
    if not isinstance(values, list):
        raise ValueError("cached exclusions must be a list")
    result: list[dict[str, str]] = []
    for value in values:
        if not isinstance(value, Mapping) or not value.get("input_id") or not value.get("reason"):
            raise ValueError("invalid cached exclusion")
        result.append({key: str(item) for key, item in value.items() if key in {"input_id", "game_id", "reason"}})
    return result
