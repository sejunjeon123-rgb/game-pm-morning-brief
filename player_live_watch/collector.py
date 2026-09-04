"""Bounded collection for verified Player Live source adapters."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime
from threading import Lock
from time import monotonic, sleep
from typing import Any

from app.config import ProjectConfig
from market_signal.normalize import content_hash, normalize_text
from player_live_watch.dcinside_adapter import listing_page_url, parse_body, parse_listing
from player_live_watch.models import CollectedPlayerPost, PlayerPostCandidate
from shared.http_client import HttpClient, HttpClientError
from shared.state_store import StateStore
from shared.time_utils import is_recent, now_kst, recent_window


DC_BROWSER_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}


class _PacedHttpClient:
    """Serialize bursty community requests while preserving the injected client API."""

    def __init__(self, client: Any, minimum_interval_seconds: float) -> None:
        self.client = client
        self.minimum_interval_seconds = minimum_interval_seconds
        self._lock = Lock()
        self._last_started = 0.0

    def get(self, url: str, *, headers: Any = None) -> Any:
        with self._lock:
            wait_seconds = self.minimum_interval_seconds - (monotonic() - self._last_started)
            if wait_seconds > 0:
                sleep(wait_seconds)
            self._last_started = monotonic()
            return self.client.get(url, headers=headers)


def _selected_candidates(candidates: tuple[PlayerPostCandidate, ...], limit: int) -> tuple[PlayerPostCandidate, ...]:
    newest = list(candidates[: max(1, limit // 2)])
    engaged = sorted(
        candidates,
        key=lambda item: (item.recommendation_count, item.comment_count, item.view_count, item.published_at),
        reverse=True,
    )
    selected: dict[str, PlayerPostCandidate] = {item.url: item for item in newest}
    for item in engaged:
        if len(selected) >= limit:
            break
        selected.setdefault(item.url, item)
    return tuple(sorted(selected.values(), key=lambda item: item.published_at, reverse=True))


def _collect_detail(http: HttpClient, candidate: PlayerPostCandidate, referer: str) -> tuple[PlayerPostCandidate, str, bool]:
    for _ in range(2):
        response = http.get(candidate.url, headers=DC_BROWSER_HEADERS | {"Referer": referer})
        if len(response.body) > 4_000_000:
            raise ValueError("post detail exceeds response size limit")
        html = response.text()
        if "write_div" in html:
            return candidate, parse_body(html), True
    raise ValueError("post detail body marker is missing after semantic retry")


def _collect_listing_page(
    http: Any,
    *,
    game_id: str,
    source: dict[str, Any],
    page: int,
) -> tuple[tuple[PlayerPostCandidate, ...], int, int]:
    page_url = listing_page_url(source["url"], page)
    semantic_retries = 0
    parsed: tuple[PlayerPostCandidate, ...] = ()
    marker_count = 0
    for semantic_attempt in range(2):
        response = http.get(
            page_url,
            headers=DC_BROWSER_HEADERS | {"Referer": source["url"]},
        )
        if len(response.body) > 2_000_000:
            raise ValueError("listing exceeds response size limit")
        listing_html = response.text()
        marker_count = listing_html.count("ub-content us-post")
        parsed = parse_listing(
            game_id,
            source["source_id"],
            source["url"],
            listing_html,
        )
        if parsed or marker_count:
            break
        if semantic_attempt == 0:
            semantic_retries += 1
    return parsed, marker_count, semantic_retries


def collect_dcinside_posts(
    config: ProjectConfig,
    state: StateStore,
    game_ids: tuple[str, ...],
    *,
    client: HttpClient | None = None,
    max_listing_pages: int = 3,
    max_details_per_game: int = 20,
    detail_workers: int = 4,
    collected_at: datetime | None = None,
    minimum_interval_seconds: float | None = None,
) -> dict[str, Any]:
    if max_listing_pages <= 0 or max_details_per_game <= 0 or detail_workers <= 0:
        raise ValueError("collection bounds must be positive")
    base_http = client or HttpClient(timeout=20, retries=2, backoff=1)
    http = _PacedHttpClient(
        base_http,
        minimum_interval_seconds if minimum_interval_seconds is not None else (0.8 if client is None else 0.0),
    )
    observed_at = collected_at or now_kst()
    window_start, _ = recent_window(now=observed_at)
    source_entries = {
        item["game_id"]: tuple(
            source
            for source in item["sources"]
            if source["platform"] == "디시인사이드" and source["collection_status"] == "ADAPTER_READY"
        )
        for item in config.player_live_sources
    }
    previous_state = state.read("player-live/dcinside_hashes", {"posts": {}})
    records = dict(previous_state.get("posts", {}))
    posts: list[CollectedPlayerPost] = []
    gaps: list[dict[str, str]] = []
    metrics: dict[str, dict[str, int | bool]] = {}

    # Secure one current listing per game before any burst of detail reads can
    # cause the public site to return an empty throttling shell.
    prefetched_first_pages: dict[
        str,
        tuple[tuple[PlayerPostCandidate, ...], int, int] | Exception,
    ] = {}
    for game_id in game_ids:
        sources = source_entries.get(game_id, ())
        if not sources:
            continue
        try:
            prefetched_first_pages[game_id] = _collect_listing_page(
                http,
                game_id=game_id,
                source=sources[0],
                page=1,
            )
        except (HttpClientError, KeyError, TypeError, ValueError, UnicodeError) as exc:
            prefetched_first_pages[game_id] = exc

    for game_id in game_ids:
        sources = source_entries.get(game_id, ())
        if not sources:
            gaps.append({"game_id": game_id, "source": "디시인사이드", "reason": "verified ADAPTER_READY source is missing"})
            continue
        source = sources[0]
        candidates: dict[str, PlayerPostCandidate] = {}
        pages_read = 0
        parsed_count = 0
        listing_marker_count = 0
        semantic_retry_count = 0
        window_truncated = False
        try:
            for page in range(1, max_listing_pages + 1):
                if page == 1:
                    first_page = prefetched_first_pages[game_id]
                    if isinstance(first_page, Exception):
                        raise first_page
                    parsed, marker_count, page_retries = first_page
                else:
                    parsed, marker_count, page_retries = _collect_listing_page(
                        http,
                        game_id=game_id,
                        source=source,
                        page=page,
                    )
                semantic_retry_count += page_retries
                listing_marker_count += marker_count
                parsed_count += len(parsed)
                pages_read += 1
                if not parsed:
                    break
                for candidate in parsed:
                    if is_recent(candidate.published_at, now=observed_at):
                        candidates[candidate.url] = candidate
                if min(item.published_at for item in parsed) < window_start:
                    break
            else:
                if candidates and min(item.published_at for item in candidates.values()) > window_start:
                    window_truncated = True
        except (HttpClientError, KeyError, TypeError, ValueError, UnicodeError) as exc:
            gaps.append({"game_id": game_id, "source": source["source_id"], "reason": f"DCInside listing collection failed: {type(exc).__name__}"})
            metrics[game_id] = {
                "pages_read": pages_read,
                "listing_marker_count": listing_marker_count,
                "parsed_count": parsed_count,
                "semantic_retry_count": semantic_retry_count,
                "candidate_count": len(candidates),
                "detail_count": 0,
                "body_marker_count": 0,
                "title_only_count": 0,
                "window_truncated": window_truncated,
            }
            continue

        selected = _selected_candidates(tuple(sorted(candidates.values(), key=lambda item: item.published_at, reverse=True)), max_details_per_game)
        detail_results: list[tuple[PlayerPostCandidate, str, bool]] = []
        detail_failure_types: list[str] = []
        with ThreadPoolExecutor(max_workers=detail_workers) as executor:
            futures = {executor.submit(_collect_detail, http, candidate, source["url"]): candidate for candidate in selected}
            for future in as_completed(futures):
                candidate = futures[future]
                try:
                    detail_results.append(future.result())
                except (HttpClientError, TypeError, ValueError, UnicodeError) as exc:
                    detail_failure_types.append(type(exc).__name__)
                    detail_results.append((candidate, "", False))

        if detail_failure_types:
            failure_types = ", ".join(sorted(set(detail_failure_types)))
            gaps.append(
                {
                    "game_id": game_id,
                    "source": source["source_id"],
                    "reason": (
                        f"{len(detail_failure_types)} of {len(selected)} selected DCInside detail bodies "
                        f"were unavailable; TITLE_ONLY evidence was preserved ({failure_types})"
                    ),
                }
            )

        for candidate, body, _ in sorted(detail_results, key=lambda item: item[0].published_at, reverse=True):
            normalized = normalize_text(f"{candidate.title}\n{body}")
            digest = content_hash(normalized)
            previous = records.get(candidate.url, {})
            post = CollectedPlayerPost(
                game_id=game_id,
                source_id=source["source_id"],
                platform=source["platform"],
                source_type=source["source_type"],
                url=candidate.url,
                title=candidate.title,
                published_at=candidate.published_at,
                collected_at=observed_at,
                normalized_text=normalized,
                content_hash=digest,
                content_availability="FULL_TEXT" if body else "TITLE_ONLY",
                comment_count=candidate.comment_count,
                view_count=candidate.view_count,
                recommendation_count=candidate.recommendation_count,
                previous_content_hash=previous.get("content_hash"),
            )
            posts.append(post)
            records[candidate.url] = {
                "game_id": game_id,
                "source_id": source["source_id"],
                "title": candidate.title,
                "content_hash": digest,
                "first_seen_at": previous.get("first_seen_at", observed_at.isoformat()),
                "last_seen_at": observed_at.isoformat(),
                "published_at": candidate.published_at.isoformat(),
            }
        if window_truncated:
            gaps.append({"game_id": game_id, "source": source["source_id"], "reason": f"recent listing window exceeded the bounded {max_listing_pages}-page scan"})
        if not candidates:
            gaps.append({"game_id": game_id, "source": source["source_id"], "reason": "no recent public posts were exposed by the verified listing"})
        metrics[game_id] = {
            "pages_read": pages_read,
            "listing_marker_count": listing_marker_count,
            "parsed_count": parsed_count,
            "semantic_retry_count": semantic_retry_count,
            "candidate_count": len(candidates),
            "detail_count": len(detail_results),
            "body_marker_count": sum(marker_present for _, _, marker_present in detail_results),
            "title_only_count": sum(not body for _, body, _ in detail_results),
            "window_truncated": window_truncated,
        }

    state.write("player-live/dcinside_hashes", {"posts": records})
    return {
        "collected_at": observed_at,
        "game_scope": game_ids,
        "adapter": "dcinside-html-v1",
        "posts": [asdict(item) | {"change_type": item.change_type} for item in posts],
        "coverage_gaps": gaps,
        "metrics": metrics,
    }
