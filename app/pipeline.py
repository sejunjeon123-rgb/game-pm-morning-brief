"""Foundation pipeline with a deterministic preview until collectors are added."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.config import ProjectConfig
from shared.schemas import MorningBrief
from shared.time_utils import now_kst


def build_preview_brief(config: ProjectConfig) -> MorningBrief:
    """Build a schema-valid no-fabrication brief for wiring tests.

    Real collection is intentionally not simulated: every core game is marked as
    having no material signal in this deterministic Foundation preview.
    """
    generated_at = now_kst()
    return MorningBrief(
        brief_date_kst=generated_at.date(),
        generated_at=generated_at,
        game_scope=config.game_ids,
        executive_summary=(
            "자동화 런타임 연결 검증용 preview입니다.",
            "실제 수집기가 연결되기 전이므로 KPI나 시장 신호를 추정하지 않습니다.",
        ),
        decisions=(),
        no_material_signal_games=config.game_ids,
    )


def brief_as_dict(brief: MorningBrief) -> dict[str, Any]:
    return asdict(brief)
