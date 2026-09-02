"""Privacy-minimized Player Live collection records.

The common evidence record deliberately keeps provenance classification
separate from platform names.  A YouTube item, for example, may be an official
fact or creator analysis depending on the configured source role.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class EvidenceClassification(StrEnum):
    """How downstream analysis may use a collected public item."""

    OFFICIAL_FACT = "OFFICIAL_FACT"
    PLAYER_CLAIM = "PLAYER_CLAIM"
    CREATOR_ANALYSIS = "CREATOR_ANALYSIS"
    UNKNOWN = "UNKNOWN"


ROLE_CLASSIFICATION = {
    "OFFICIAL_FACT": EvidenceClassification.OFFICIAL_FACT,
    "OFFICIAL_COMMUNITY_REACTION": EvidenceClassification.PLAYER_CLAIM,
    "PLAYER_REACTION": EvidenceClassification.PLAYER_CLAIM,
    "CREATOR_ANALYSIS": EvidenceClassification.CREATOR_ANALYSIS,
}


def classification_for_role(evidence_role: str) -> EvidenceClassification:
    """Map a verified source role to a non-inferential evidence boundary."""

    return ROLE_CLASSIFICATION.get(evidence_role, EvidenceClassification.UNKNOWN)


@dataclass(frozen=True, slots=True)
class PlayerPostCandidate:
    game_id: str
    source_id: str
    url: str
    title: str
    published_at: datetime
    comment_count: int = 0
    view_count: int = 0
    recommendation_count: int = 0


@dataclass(frozen=True, slots=True)
class CollectedPlayerPost:
    game_id: str
    source_id: str
    platform: str
    source_type: str
    url: str
    title: str
    published_at: datetime
    collected_at: datetime
    normalized_text: str
    content_hash: str
    content_availability: str
    comment_count: int = 0
    view_count: int = 0
    recommendation_count: int = 0
    previous_content_hash: str | None = None

    @property
    def change_type(self) -> str:
        if self.previous_content_hash is None:
            return "NEW"
        if self.previous_content_hash != self.content_hash:
            return "MODIFIED"
        return "UNCHANGED"


@dataclass(frozen=True, slots=True)
class CollectedPlayerEvidence:
    """Source-neutral evidence passed to Player Live analysis.

    No author, profile, account, IP, or comment-author fields are permitted in
    this record. Engagement values are retained only as source-specific
    observations and must not be interpreted as population sentiment.
    """

    evidence_id: str
    game_id: str
    source_id: str
    platform: str
    source_type: str
    evidence_role: str
    classification: EvidenceClassification
    url: str
    source_host: str
    title: str
    published_at: datetime
    collected_at: datetime
    normalized_text: str
    content_hash: str
    content_availability: str
    comment_count: int | None = None
    view_count: int | None = None
    recommendation_count: int | None = None
    previous_content_hash: str | None = None

    @property
    def change_type(self) -> str:
        if self.previous_content_hash is None:
            return "NEW"
        if self.previous_content_hash != self.content_hash:
            return "MODIFIED"
        return "UNCHANGED"
