"""Stable cross-skill data contracts for GAME PM Morning Brief."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any
from urllib.parse import urlsplit


class SignalCategory(StrEnum):
    UPDATE = "UPDATE"
    CHARACTER = "CHARACTER"
    BM = "BM"
    EVENT = "EVENT"
    WEB_EVENT = "WEB_EVENT"
    COLLAB = "COLLAB"
    MARKETING = "MARKETING"
    MAINTENANCE = "MAINTENANCE"
    NOTICE = "NOTICE"


class BMItemType(StrEnum):
    GROWTH = "GROWTH"
    GACHA = "GACHA"
    CURRENCY = "CURRENCY"
    EQUIPMENT = "EQUIPMENT"
    CHARACTER = "CHARACTER"
    CONVENIENCE = "CONVENIENCE"
    CONTENT_ACCESS = "CONTENT_ACCESS"
    COSMETIC = "COSMETIC"
    OTHER = "OTHER"


class Severity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SourceType(StrEnum):
    OFFICIAL_HOMEPAGE = "OFFICIAL_HOMEPAGE"
    OFFICIAL_COMMUNITY = "OFFICIAL_COMMUNITY"
    OFFICIAL_NOTICE = "OFFICIAL_NOTICE"
    OFFICIAL_YOUTUBE = "OFFICIAL_YOUTUBE"
    PUBLIC_COMMUNITY = "PUBLIC_COMMUNITY"
    PUBLIC_PLATFORM = "PUBLIC_PLATFORM"
    LIVE_INDICATOR = "LIVE_INDICATOR"


class RouteTarget(StrEnum):
    NONE = "NONE"
    PLAYER_LIVE_WATCH = "player-live-watch"


class PlayerTopic(StrEnum):
    GAMEPLAY = "GAMEPLAY"
    BALANCE = "BALANCE"
    BM = "BM"
    REWARD = "REWARD"
    CONTENT = "CONTENT"
    CHARACTER = "CHARACTER"
    BUG = "BUG"
    PERFORMANCE = "PERFORMANCE"
    ACCESS = "ACCESS"
    MAINTENANCE = "MAINTENANCE"
    COMMUNICATION = "COMMUNICATION"
    EVENT = "EVENT"
    COLLAB = "COLLAB"
    OTHER = "OTHER"


class PlayerReaction(StrEnum):
    POSITIVE = "POSITIVE"
    MIXED = "MIXED"
    NEGATIVE = "NEGATIVE"
    UNCLEAR = "UNCLEAR"


class InsightTrend(StrEnum):
    EMERGING = "EMERGING"
    RISING = "RISING"
    STABLE = "STABLE"
    FADING = "FADING"
    RESOLVED = "RESOLVED"
    UNKNOWN = "UNKNOWN"


class Confidence(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class DecisionPriority(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class DecisionDisposition(StrEnum):
    ESCALATE = "ESCALATE"
    ACT = "ACT"
    VERIFY = "VERIFY"
    MONITOR = "MONITOR"
    NO_ACTION = "NO_ACTION"


class BusinessImpactDimension(StrEnum):
    PLAYER_EXPERIENCE = "PLAYER_EXPERIENCE"
    LIVE_OPERATIONS = "LIVE_OPERATIONS"
    BM = "BM"
    TRUST_REPUTATION = "TRUST_REPUTATION"
    COMPETITIVE_TIMING = "COMPETITIVE_TIMING"


class AnalysisScope(StrEnum):
    CORE = "CORE"
    GAME_RADAR = "GAME_RADAR"


APPROVED_PM_TERMS = frozenset({
    "DAU", "NRU", "Gross", "Sales", "Net gross", "Net sales", "PU", "BU",
    "NPU", "MPU", "PUR", "BUR", "MPUR", "ARPPU", "ARPDAU", "Retention",
    "Organic", "Non organic", "CU", "MCU", "UV", "TS", "KPI", "LTV", "PLC",
    "BEP", "ROI", "CAC", "CRC", "RS", "LF", "MG", "MOU",
})


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class Evidence:
    evidence_id: str
    source_type: SourceType
    url: str
    title: str
    published_at: datetime
    collected_at: datetime
    content_hash: str
    modified_at: datetime | None = None
    previous_content_hash: str | None = None

    def __post_init__(self) -> None:
        _require_aware(self.published_at, "published_at")
        _require_aware(self.collected_at, "collected_at")
        if self.modified_at is not None:
            _require_aware(self.modified_at, "modified_at")
        if not self.url.startswith(("https://", "http://")):
            raise ValueError("evidence url must be absolute HTTP(S)")

    @property
    def is_modified(self) -> bool:
        return bool(self.previous_content_hash and self.previous_content_hash != self.content_hash)


@dataclass(frozen=True, slots=True)
class PMMetricContext:
    terms: tuple[str, ...] = ()
    rationale: str = ""
    verification_needed: bool = True

    def __post_init__(self) -> None:
        unknown = set(self.terms) - APPROVED_PM_TERMS
        if unknown:
            raise ValueError(f"unapproved PM metric terms: {sorted(unknown)}")


@dataclass(frozen=True, slots=True)
class RoutingHint:
    target: RouteTarget = RouteTarget.NONE
    deep_dive_required: bool = False
    reason: str = ""
    final_router: str = "pm-decision-lead"


@dataclass(frozen=True, slots=True)
class Signal:
    signal_id: str
    event_key: str
    game_id: str
    title: str
    summary: str
    category: SignalCategory
    severity: Severity
    observed_at: datetime
    evidence: tuple[Evidence, ...]
    source_conflicts: tuple[str, ...] = ()
    pm_metric_context: PMMetricContext = field(default_factory=PMMetricContext)
    bm_item_types: tuple[BMItemType, ...] = ()
    routing: RoutingHint = field(default_factory=RoutingHint)

    def __post_init__(self) -> None:
        _require_aware(self.observed_at, "observed_at")
        if not self.evidence:
            raise ValueError("a Signal requires at least one Evidence item")
        should_route = self.severity in {Severity.HIGH, Severity.CRITICAL}
        if should_route and not (self.routing.target is RouteTarget.PLAYER_LIVE_WATCH and self.routing.deep_dive_required):
            raise ValueError("HIGH/CRITICAL signals must request player-live-watch deep dive")
        if self.category is not SignalCategory.BM and self.bm_item_types:
            raise ValueError("bm_item_types are allowed only for BM signals")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PlayerLiveInsight:
    insight_id: str
    issue_key: str
    game_id: str
    title: str
    summary: str
    topic: PlayerTopic
    reaction: PlayerReaction
    intensity: Severity
    trend: InsightTrend
    confidence: Confidence
    observed_at: datetime
    evidence: tuple[Evidence, ...]
    source_signal_ids: tuple[str, ...] = ()
    observed_facts: tuple[str, ...] = ()
    player_claims: tuple[str, ...] = ()
    analysis: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    pm_metric_context: PMMetricContext = field(default_factory=PMMetricContext)
    live_risk: str = ""
    recommended_checks: tuple[str, ...] = ()
    routing: RoutingHint = field(default_factory=RoutingHint)
    analysis_scope: AnalysisScope = AnalysisScope.CORE

    def __post_init__(self) -> None:
        _require_aware(self.observed_at, "observed_at")
        if not self.evidence:
            raise ValueError("a PlayerLiveInsight requires at least one Evidence item")
        if self.routing.final_router != "pm-decision-lead":
            raise ValueError("PlayerLiveInsight final router must be pm-decision-lead")
        if self.analysis_scope is AnalysisScope.GAME_RADAR:
            source_hosts = {
                urlsplit(item.url).netloc.lower()
                for item in self.evidence
                if urlsplit(item.url).netloc
            }
            if len(source_hosts) < 2:
                raise ValueError("GAME_RADAR insight requires at least two independent source hosts")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class MetricCheck:
    term: str
    question: str
    comparison_period: str = ""
    segment: str = ""

    def __post_init__(self) -> None:
        if self.term not in APPROVED_PM_TERMS:
            raise ValueError(f"unapproved PM metric term: {self.term}")
        if not self.question:
            raise ValueError("MetricCheck question is required")


@dataclass(frozen=True, slots=True)
class RecommendedAction:
    action: str
    suggested_role: str
    timing: str
    dependency: str = ""
    reassessment_condition: str = ""

    def __post_init__(self) -> None:
        if not self.action or not self.suggested_role or not self.timing:
            raise ValueError("action, suggested_role, and timing are required")
        if not self.reassessment_condition:
            raise ValueError("recommended action requires a reassessment condition")


@dataclass(frozen=True, slots=True)
class PMDecisionItem:
    decision_id: str
    decision_key: str
    game_id: str
    title: str
    executive_summary: str
    priority: DecisionPriority
    disposition: DecisionDisposition
    confidence: Confidence
    decided_at: datetime
    evidence: tuple[Evidence, ...]
    source_signal_ids: tuple[str, ...] = ()
    source_insight_ids: tuple[str, ...] = ()
    observed_facts: tuple[str, ...] = ()
    interpretation: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    business_impact: tuple[BusinessImpactDimension, ...] = ()
    pm_metric_context: PMMetricContext = field(default_factory=PMMetricContext)
    metric_checks: tuple[MetricCheck, ...] = ()
    recommended_actions: tuple[RecommendedAction, ...] = ()
    watch_conditions: tuple[str, ...] = ()
    decision_rationale: str = ""
    analysis_scope: AnalysisScope = AnalysisScope.CORE

    def __post_init__(self) -> None:
        _require_aware(self.decided_at, "decided_at")
        if not self.evidence:
            raise ValueError("a PMDecisionItem requires at least one Evidence item")
        if self.priority is DecisionPriority.P0 and self.disposition not in {
            DecisionDisposition.ESCALATE,
            DecisionDisposition.ACT,
        }:
            raise ValueError("P0 requires ESCALATE or ACT disposition")
        if not self.decision_rationale:
            raise ValueError("decision_rationale is required")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class MorningBrief:
    brief_date_kst: date
    generated_at: datetime
    game_scope: tuple[str, ...]
    executive_summary: tuple[str, ...]
    decisions: tuple[PMDecisionItem, ...]
    immediate_attention: tuple[str, ...] = ()
    today_checks: tuple[str, ...] = ()
    watchlist: tuple[str, ...] = ()
    data_gaps: tuple[str, ...] = ()
    coverage_gaps: tuple[str, ...] = ()
    no_material_signal_games: tuple[str, ...] = ()
    radar_games: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_aware(self.generated_at, "generated_at")
        decision_ids = {item.decision_id for item in self.decisions}
        referenced_ids = set(self.immediate_attention + self.today_checks + self.watchlist)
        unknown_ids = referenced_ids - decision_ids
        if unknown_ids:
            raise ValueError(f"brief sections reference unknown decisions: {sorted(unknown_ids)}")
        core_decision_games = {
            item.game_id
            for item in self.decisions
            if item.analysis_scope is AnalysisScope.CORE
        }
        radar_decision_games = {
            item.game_id
            for item in self.decisions
            if item.analysis_scope is AnalysisScope.GAME_RADAR
        }
        covered_games = (
            core_decision_games
            | set(self.no_material_signal_games)
            | set(self.coverage_gaps)
        )
        if covered_games != set(self.game_scope):
            raise ValueError("every scoped game must be decided, clear, or listed as a coverage gap")
        if len(self.radar_games) > 3:
            raise ValueError("a MorningBrief may include at most three GAME_RADAR games")
        if set(self.radar_games) & set(self.game_scope):
            raise ValueError("GAME_RADAR games must be outside the configured core game scope")
        if radar_decision_games != set(self.radar_games):
            raise ValueError("radar_games and GAME_RADAR decision games must match")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
