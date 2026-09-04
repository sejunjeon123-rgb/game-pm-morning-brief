"""Bounded public HTML fallback; no API keys, relative-date guesses or transcripts."""

import json
import re
from datetime import datetime
from urllib.parse import urljoin, urlsplit

from market_signal.models import CollectedNotice
from market_signal.normalize import content_hash, normalize_text
from shared.http_client import HttpClientError
from shared.time_utils import ensure_kst, is_recent


def embedded_json(html, name):
    match = re.search(r"(?:var\s+)?" + re.escape(name) + r"\s*=\s*", html)
    if not match:
        raise ValueError("missing public metadata")
    value, _ = json.JSONDecoder().raw_decode(html[match.end():])
    if not isinstance(value, dict):
        raise ValueError("invalid public metadata")
    return value


def values_for(node, key):
    if isinstance(node, dict):
        if key in node:
            yield node[key]
        for value in node.values():
            yield from values_for(value, key)
    elif isinstance(node, list):
        for value in node:
            yield from values_for(value, key)


def channel_data(http, url, channel_id):
    if urlsplit(url).hostname != "www.youtube.com":
        raise ValueError("unapproved channel host")
    data = embedded_json(http.get(url).text(), "ytInitialData")
    if data.get("metadata", {}).get("channelMetadataRenderer", {}).get("externalId") != channel_id:
        raise ValueError("channel identity mismatch")
    return data


def parse_watch(html, game_id, channel_id, video_id, now, filter_terms=(), *, diagnostics=None):
    def excluded(reason):
        if diagnostics is not None:
            diagnostics[reason] = diagnostics.get(reason, 0) + 1
        return None
    data = embedded_json(html, "ytInitialPlayerResponse")
    details = data.get("videoDetails", {})
    meta = data.get("microformat", {}).get("playerMicroformatRenderer", {})
    if details.get("channelId") != channel_id or details.get("videoId") != video_id:
        raise ValueError("video identity mismatch")
    if data.get("playabilityStatus", {}).get("status") != "OK":
        return excluded("unavailable")
    if details.get("isLiveContent"):
        return excluded("shorts_or_live")
    # Only an explicit timezone-aware publication timestamp is admissible.
    # Date-only, relative ages, upload dates and upcoming premieres are not substitutes.
    published = ensure_kst(datetime.fromisoformat(meta.get("publishDate", "").replace("Z", "+00:00")))
    if not is_recent(published, now=now):
        return excluded("future" if published > now else "outside_window")
    title = normalize_text(details.get("title", ""))
    description = normalize_text(details.get("shortDescription", ""))[:1800]
    text = normalize_text(f"{title}\n{description}")
    if not title or (filter_terms and not any(term.casefold() in text.casefold() for term in filter_terms)):
        return excluded("empty_or_unmatched")
    return CollectedNotice(game_id, f"https://www.youtube.com/watch?v={video_id}",
                           title, published, now, text, content_hash(text),
                           source_type="OFFICIAL_YOUTUBE")


def video_card_ids(contents):
    """Read video cards only, not playback queues or recommendation actions."""
    if isinstance(contents, dict):
        for key, value in contents.items():
            if key == "videoRenderer" and isinstance(value, dict):
                yield value.get("videoId")
            elif key == "lockupViewModel" and isinstance(value, dict):
                if value.get("contentType") == "LOCKUP_CONTENT_TYPE_VIDEO":
                    yield value.get("contentId")
            else:
                yield from video_card_ids(value)
    elif isinstance(contents, list):
        for value in contents:
            yield from video_card_ids(value)


def collect_channel_fallback(http, source, now, *, max_videos=3, diagnostics=None):
    if not isinstance(max_videos, int) or not 1 <= max_videos <= 3:
        raise ValueError("video detail limit must be between 1 and 3")
    stats = diagnostics if diagnostics is not None else {}
    channel_id = source["youtube_channel_id"]
    data = channel_data(http, source["youtube"], channel_id)
    for tab in values_for(data.get("contents", {}), "tabRenderer"):
        endpoint = tab.get("endpoint", {})
        path = endpoint.get("commandMetadata", {}).get("webCommandMetadata", {}).get("url", "")
        if path.endswith("/videos") and endpoint.get("browseEndpoint", {}).get("browseId") == channel_id:
            if not tab.get("selected"):
                data = channel_data(http, urljoin(source["youtube"], path), channel_id)
            break
    else:
        raise ValueError("verified video tab missing")
    contents = data.get("contents", {})
    selected = [t for t in values_for(contents, "tabRenderer") if t.get("selected")]
    if selected:
        contents = selected[0].get("content", {})
    ids = list(dict.fromkeys(v for v in video_card_ids(contents)
                            if isinstance(v, str) and re.fullmatch(r"[A-Za-z0-9_-]{11}", v)))[:max_videos]
    stats["candidates"] = len(ids)
    items = []
    for video_id in ids:
        try:
            html = http.get(f"https://www.youtube.com/watch?v={video_id}").text()
            item = parse_watch(html, source["game_id"], channel_id, video_id, now,
                               tuple(source.get("youtube_filter_terms", ())), diagnostics=stats)
            if item:
                items.append(item)
        except HttpClientError:
            stats["request_failed"] = stats.get("request_failed", 0) + 1
        except (ValueError, TypeError, AttributeError):
            stats["invalid_metadata"] = stats.get("invalid_metadata", 0) + 1
    stats["accepted"] = len(items)
    return tuple(items)


def fallback_summary(stats):
    """Only fixed labels and counts: never echo page text or exception content."""
    labels = {"candidates": "확인 대상", "accepted": "최근 영상 수집",
              "outside_window": "7일 이전", "future": "미래 게시일",
              "unavailable": "영상 접근 불가", "shorts_or_live": "Shorts·라이브 제외",
              "empty_or_unmatched": "내용 없음·게임 불일치", "request_failed": "요청 실패",
              "invalid_metadata": "게시일·신원 등 메타데이터 확인 불가", "channel_failed": "채널 목록 확인 실패"}
    return "; ".join(f"{label}={stats[key]}" for key, label in labels.items() if key in stats)
