"""Internal deterministic collection records before Signal analysis."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class NoticeCandidate:
    game_id: str
    url: str
    title: str
    published_at: datetime


@dataclass(frozen=True, slots=True)
class CollectedNotice:
    game_id: str
    url: str
    title: str
    published_at: datetime
    collected_at: datetime
    normalized_text: str
    content_hash: str
    previous_content_hash: str | None = None
    source_type: str = "OFFICIAL_NOTICE"

    @property
    def change_type(self) -> str:
        if self.previous_content_hash is None:
            return "NEW"
        if self.previous_content_hash != self.content_hash:
            return "MODIFIED"
        return "UNCHANGED"
