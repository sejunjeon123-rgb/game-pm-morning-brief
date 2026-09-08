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
        return "근거 부족 · 공식 자료와 공개 커뮤니티 표본을 모두 확보하지 못했습니다."
    if game in brief.get("no_material_signal_games", []):
        return "확보한 자료에서 추가 중요 변경이 확인되지 않았습니다."
    return "이번 보고서에 포함된 분석 항목이 없습니다."


def game_headline_summaries(brief, *, limit=None, detailed=False):
    """Build evidence-bounded, conclusion-first summaries without another AI call."""
    rows = list(report_games(brief))
    if limit is not None:
        # Slack gives scarce space to games with an actual decision first, while
        # preserving the configured order inside each group.
        rows = [row for row in rows if row[1]] + [row for row in rows if not row[1]]
        rows = rows[:limit]
    summaries = []
    for game, items in rows:
        name = game.get("report_name", game["name_ko"])
        if not items:
            if game["id"] in brief.get("coverage_gaps", []):
                summaries.append(f"{name} — 자료 확인 제한: 공식 자료와 유효한 공개 반응을 충분히 확보하지 못했습니다.")
            else:
                summaries.append(f"{name} — 주요 변화 없음: 확보한 자료에서 추가로 보고할 중요 변경이 확인되지 않았습니다.")
            continue
        item = items[0]
        topic = str(item.get("title", "주요 변화 확인")).split(" · ", 1)[-1]
        lead = str(item.get("executive_summary", "확인 가능한 주요 변화를 검토했습니다.")).strip()
        text = f"{name} — {topic}: {lead}"
        if detailed:
            interpretation = item.get("interpretation") or []
            if interpretation:
                text += f" 사업 관점 해석: {interpretation[0]}"
            elif item.get("unknowns"):
                text += f" 추가 확인: {item['unknowns'][0]}"
        summaries.append(text)
    return summaries


COLLECTION_SCOPE_NOTICE = (
    "최근 7일의 공식 공지와 공개 이용자 반응을 중심으로 작성했습니다. "
    "YouTube는 게시일과 출처가 확인된 영상만 반영했으며, "
    "공개 반응은 전체 이용자를 대표하지 않습니다."
)
