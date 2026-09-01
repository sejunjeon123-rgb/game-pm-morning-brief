"""Canonical PM terminology and deterministic semantic checks.

The definitions here are business meanings, not benchmark targets or accounting
assumptions.  Public-source analysis may only propose an internal verification;
it cannot establish a KPI value or direction.
"""

from __future__ import annotations

import re
from typing import Iterable


PM_TERM_DEFINITIONS: dict[str, str] = {
    "DAU": "일간 활성 사용자 수",
    "NRU": "신규 등록 사용자 수",
    "Gross": "공제 전 총매출",
    "Sales": "게임에서 발생한 매출",
    "Net gross": "계약과 회계 기준에 따른 공제 후 순매출",
    "Net sales": "계약과 회계 기준에 따른 공제 후 순매출",
    "PU": "일간 결제 사용자 수",
    "BU": "일간 구매 사용자 수",
    "NPU": "신규 결제 사용자 수",
    "MPU": "월간 결제 사용자 수",
    "PUR": "DAU 중 일간 결제 사용자 비율(PU / DAU)",
    "BUR": "DAU 중 일간 구매 사용자 비율(BU / DAU)",
    "MPUR": "MAU 중 월간 결제 사용자 비율(MPU / MAU)",
    "ARPPU": "결제 사용자 1인당 평균 매출(Sales / PU)",
    "ARPDAU": "일간 활성 사용자 1인당 평균 매출(Sales / DAU)",
    "Retention": "기준 코호트가 이후 시점에 다시 이용한 비율",
    "Organic": "유료 마케팅 기여 없이 발생한 자연 유입",
    "Non organic": "광고·캠페인 등 마케팅 기여로 발생한 유입",
    "CU": "특정 시점의 동시 접속 사용자 수",
    "MCU": "측정 기간 중 최고 동시 접속 사용자 수",
    "UV": "측정 기간에 웹 자산을 방문한 중복 제거 사용자 수",
    "TS": "사용자의 게임 이용 시간",
    "KPI": "목표 달성도를 판단하기 위해 합의한 핵심 성과 지표",
    "LTV": "사용자 생애 동안 기대되는 경제적 가치",
    "PLC": "제품 수명주기 또는 문맥상 콘텐츠 소비 수명주기",
    "BEP": "수익과 비용이 같아지는 손익분기점",
    "ROI": "투자 대비 수익성",
    "CAC": "사용자 1인을 획득하는 데 든 비용",
    "CRC": "사용자 1인을 유지하는 데 든 비용",
    "RS": "계약 당사자 사이의 수익 배분 비율",
    "LF": "라이선스 또는 퍼블리싱 계약에서 지급하는 계약금",
    "MG": "계약상 보장하는 최소 수익 또는 선급 보장금",
    "MOU": "거래·협력의 기본 합의를 기록한 양해각서",
}

APPROVED_PM_TERMS = frozenset(PM_TERM_DEFINITIONS)

_SEMANTIC_CUES: dict[str, re.Pattern[str]] = {
    "DAU": re.compile(r"일간.{0,8}(활성|접속|방문)|DAU", re.I),
    "NRU": re.compile(r"신규.{0,8}(등록|가입|유입)|NRU", re.I),
    "Gross": re.compile(r"총매출|공제\s*전.{0,6}매출|Gross", re.I),
    "Sales": re.compile(r"매출|판매\s*실적|Sales", re.I),
    "Net gross": re.compile(r"순매출|공제\s*후.{0,6}매출|Net\s*gross", re.I),
    "Net sales": re.compile(r"순매출|공제\s*후.{0,6}매출|Net\s*sales", re.I),
    "PU": re.compile(r"(일간.{0,8})?(결제|구매).{0,6}(사용자|유저|이용자|인원)|paying\s*user", re.I),
    "BU": re.compile(r"(일간.{0,8})?구매.{0,6}(사용자|유저|이용자|인원)|buying\s*user", re.I),
    "NPU": re.compile(r"신규.{0,8}결제.{0,6}(사용자|유저|이용자|인원)|new.{0,8}paying\s*user", re.I),
    "MPU": re.compile(r"월간.{0,8}결제.{0,6}(사용자|유저|이용자|인원)|monthly.{0,8}paying\s*user", re.I),
    "PUR": re.compile(r"(일간.{0,8})?결제.{0,8}(비율|전환율)|결제율|PU\s*/\s*DAU", re.I),
    "BUR": re.compile(r"(일간.{0,8})?구매.{0,8}(비율|전환율)|구매율|BU\s*/\s*DAU", re.I),
    "MPUR": re.compile(r"월간.{0,8}결제.{0,8}(비율|전환율)|월\s*결제율|MPU\s*/\s*MAU", re.I),
    "ARPPU": re.compile(r"결제.{0,8}(1인당|사용자당|유저당).{0,8}(평균\s*)?(매출|결제)|객단가|Sales\s*/\s*PU", re.I),
    "ARPDAU": re.compile(r"(일간\s*)?(활성|방문).{0,8}(1인당|사용자당|유저당).{0,8}(평균\s*)?(매출|결제)|Sales\s*/\s*DAU", re.I),
    "Retention": re.compile(r"잔존|재방문|리텐션|코호트.{0,8}(복귀|유지)|Retention", re.I),
    "Organic": re.compile(r"자연\s*유입|마케팅\s*없이|Organic", re.I),
    "Non organic": re.compile(r"광고\s*유입|유료\s*유입|마케팅.{0,8}유입|Non\s*organic", re.I),
    "CU": re.compile(r"동시\s*접속(자|사용자|유저|인원)?|concurrent\s*user", re.I),
    "MCU": re.compile(r"(최고|최대|피크).{0,8}동시\s*접속|maximum\s*concurrent", re.I),
    "UV": re.compile(r"순\s*방문(자|사용자|유저)?|중복\s*제거.{0,8}방문|unique\s*visitor", re.I),
    "TS": re.compile(r"이용\s*시간|플레이\s*시간|체류\s*시간|time\s*spend", re.I),
    "KPI": re.compile(r"핵심.{0,8}(성과|지표)|성과.{0,8}지표|KPI", re.I),
    "LTV": re.compile(r"생애.{0,8}(가치|매출|수익)|이탈.{0,12}누적.{0,8}(매출|가치)|LTV", re.I),
    "PLC": re.compile(r"제품\s*수명|수명\s*주기|콘텐츠\s*소비.{0,8}(속도|주기)|PLC", re.I),
    "BEP": re.compile(r"손익\s*분기|BEP", re.I),
    "ROI": re.compile(r"투자.{0,8}(대비|수익)|투자\s*수익률|ROI", re.I),
    "CAC": re.compile(r"(사용자|유저|고객).{0,8}획득.{0,8}비용|CAC", re.I),
    "CRC": re.compile(r"(사용자|유저|고객).{0,8}유지.{0,8}비용|CRC", re.I),
    "RS": re.compile(r"수익\s*배분|revenue\s*share|RS", re.I),
    "LF": re.compile(r"라이선스.{0,8}(계약금|수수료)|퍼블리싱.{0,8}계약금|license\s*fee|LF", re.I),
    "MG": re.compile(r"최소.{0,8}(수익\s*)?보장|선급\s*보장금|minimum\s*guarantee|MG", re.I),
    "MOU": re.compile(r"양해\s*각서|memorandum\s*of\s*understanding|MOU", re.I),
}

_VERIFICATION_CUE = re.compile(r"확인|검증|점검|추적|모니터링|살펴볼|비교", re.I)
_UNSUPPORTED_DIRECTION = re.compile(
    r"(DAU|NRU|매출|순매출|결제율|잔존율|Retention|ARPPU|ARPDAU|LTV|CU|MCU).{0,12}"
    r"(증가했다|감소했다|상승했다|하락했다|개선됐다|악화됐다|급증했다|급감했다)",
    re.I,
)
_HANGUL = re.compile(r"[가-힣]")


def is_korean_prose(value: str) -> bool:
    """Return true when prose is materially Korean, allowing names and acronyms."""
    hangul = len(_HANGUL.findall(value))
    latin = len(re.findall(r"[A-Za-z]", value))
    return hangul >= 2 and hangul * 4 >= latin


def invalid_pm_term_meanings(terms: Iterable[str], rationale: str) -> tuple[str, ...]:
    """Identify terms whose rationale does not express their canonical meaning."""
    return tuple(
        term
        for term in terms
        if term not in _SEMANTIC_CUES or not _SEMANTIC_CUES[term].search(rationale)
    )


def is_pm_verification_rationale(rationale: str) -> bool:
    """Require Korean verification wording and reject unsupported KPI direction."""
    return bool(
        is_korean_prose(rationale)
        and _VERIFICATION_CUE.search(rationale)
        and not _UNSUPPORTED_DIRECTION.search(rationale)
    )


def sanitize_pm_metric_context(terms: Iterable[str], rationale: str) -> tuple[tuple[str, ...], str]:
    """Drop ambiguous or asserted KPI references from public-source analysis."""
    ordered = tuple(dict.fromkeys(str(term) for term in terms if str(term) in APPROVED_PM_TERMS))
    cleaned_rationale = " ".join(str(rationale).split())
    if (
        not ordered
        or not is_pm_verification_rationale(cleaned_rationale)
    ):
        return (), ""
    invalid = set(invalid_pm_term_meanings(ordered, cleaned_rationale))
    valid = tuple(term for term in ordered if term not in invalid)
    return (valid, cleaned_rationale) if valid else ((), "")
