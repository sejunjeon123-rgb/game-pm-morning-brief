"""Official notice collection with bounded requests and coverage reporting."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.config import ProjectConfig
from market_signal.listing_parser import parse_listing
from market_signal.models import CollectedNotice
from market_signal.normalize import content_hash, extract_text, extract_text_from_class
from market_signal.official_board_adapters import ADAPTER_SPECS, OfficialDocument, collect_official_board
from shared.http_client import HttpClient, HttpClientError
from shared.state_store import StateStore
from shared.time_utils import is_recent, now_kst


HTML_GAMES = frozenset({"mabinogi-mobile", "black-desert-mobile"})
SUPPORTED_GAMES = HTML_GAMES | frozenset(ADAPTER_SPECS)


def collect_official_notices(
    config: ProjectConfig,
    state: StateStore,
    game_ids: tuple[str, ...],
    *,
    client: HttpClient | None = None,
    max_details_per_game: int = 20,
) -> dict[str, Any]:
    http = client or HttpClient(timeout=20, retries=2, backoff=1)
    source_by_game = {item["game_id"]: item for item in config.sources}
    collected_at = now_kst()
    notices: list[CollectedNotice] = []
    coverage_gaps: list[dict[str, str]] = []
    next_state = state.read("market-signal/notice_hashes", {"notices": {}})
    records = dict(next_state.get("notices", {}))

    for game_id in game_ids:
        if game_id not in SUPPORTED_GAMES:
            coverage_gaps.append({"game_id": game_id, "source": "OFFICIAL_NOTICE", "reason": "V1 collector adapter is not implemented"})
            continue
        source = source_by_game[game_id]
        try:
            if game_id in ADAPTER_SPECS:
                documents = tuple(item for item in collect_official_board(game_id, http, rows=max_details_per_game) if is_recent(item.published_at))
            else:
                list_url = source["notices"]
                listing = http.get(list_url).text()
                candidates = tuple(item for item in parse_listing(game_id, list_url, listing) if is_recent(item.published_at))
                documents = _collect_html_documents(game_id, candidates[:max_details_per_game], http)
        except (HttpClientError, KeyError, TypeError, ValueError) as exc:
            coverage_gaps.append({"game_id": game_id, "source": "OFFICIAL_NOTICE", "reason": f"notice list collection failed: {type(exc).__name__}"})
            continue
        if not documents:
            coverage_gaps.append({"game_id": game_id, "source": "OFFICIAL_NOTICE", "reason": "no recent official notice documents were exposed by the verified adapter"})
            continue
        for document in documents[:max_details_per_game]:
            normalized = document.normalized_text
            digest = content_hash(normalized)
            previous = records.get(document.url, {})
            notice = CollectedNotice(
                game_id=game_id,
                url=document.url,
                title=document.title,
                published_at=document.published_at,
                collected_at=collected_at,
                normalized_text=normalized,
                content_hash=digest,
                previous_content_hash=previous.get("content_hash"),
                source_type=document.source_type,
            )
            notices.append(notice)
            state_record = {
                "game_id": game_id,
                "title": document.title,
                "content_hash": digest,
                "first_seen_at": previous.get("first_seen_at", collected_at.isoformat()),
                "last_seen_at": collected_at.isoformat(),
                "published_at": document.published_at.isoformat(),
            }
            if previous.get("content_hash") and previous.get("content_hash") != digest:
                state_record["modified_at"] = collected_at.isoformat()
                state_record["previous_content_hash"] = previous["content_hash"]
            elif previous.get("modified_at"):
                state_record["modified_at"] = previous["modified_at"]
                state_record["previous_content_hash"] = previous.get("previous_content_hash")
            records[document.url] = state_record

    state.write("market-signal/notice_hashes", {"notices": records})
    return {
        "collected_at": collected_at,
        "game_scope": game_ids,
        "notices": [
            asdict(item) | {"change_type": item.change_type}
            for item in notices
        ],
        "coverage_gaps": coverage_gaps,
    }


def _collect_html_documents(game_id: str, candidates: tuple[Any, ...], http: HttpClient) -> tuple[OfficialDocument, ...]:
    documents: list[OfficialDocument] = []
    for candidate in candidates:
        detail_html = http.get(candidate.url).text()
        normalized = extract_text_from_class(detail_html, "contents_area") if game_id == "black-desert-mobile" else extract_text(detail_html)
        if normalized:
            documents.append(OfficialDocument(game_id, candidate.url, candidate.title, candidate.published_at, normalized, "OFFICIAL_HOMEPAGE"))
    return tuple(documents)
