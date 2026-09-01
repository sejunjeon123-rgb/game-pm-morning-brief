"""Privacy-minimized Player Live collection records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


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

