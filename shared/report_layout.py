"""Presentation order only; does not reprioritize analytical decisions."""
import json
from pathlib import Path


GROUP_ICONS = {"생활형 MMORPG": "🌿", "리니지라이크 MMORPG": "⚔️",
               "턴제 수집형 RPG": "♟️", "서브컬처 수집형 RPG": "🎨"}


def group_title(group):
    return f"{GROUP_ICONS.get(group, '🎮')} {group}"


def report_games(brief):
    games = json.loads((Path(__file__).resolve().parents[1] / "config/games.json").read_text(encoding="utf-8"))["games"]
    scope = set(brief.get("game_scope", [g["id"] for g in games]))
    for game in games:
        if game["id"] in scope:
            yield game, [d for d in brief.get("decisions", []) if d["game_id"] == game["id"]]


def empty_status(brief, game):
    if game in brief.get("coverage_gaps", []):
        return "근거 부족 · 수집 또는 분석 공백으로 주요 소식을 확정하지 못했습니다."
    if game in brief.get("no_material_signal_games", []):
        return "확보한 자료에서 추가 중요 변경이 확인되지 않았습니다."
    return "이번 보고서에 포함된 분석 항목이 없습니다."
