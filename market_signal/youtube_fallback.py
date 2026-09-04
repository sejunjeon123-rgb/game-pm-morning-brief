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


def parse_watch(html, game_id, channel_id, video_id, now, filter_terms=()):
    data = embedded_json(html, "ytInitialPlayerResponse")
    details = data.get("videoDetails", {})
    meta = data.get("microformat", {}).get("playerMicroformatRenderer", {})
    if details.get("channelId") != channel_id or details.get("videoId") != video_id:
        raise ValueError("video identity mismatch")
    if data.get("playabilityStatus", {}).get("status") != "OK" or details.get("isLiveContent"):
        return None
    # Only an explicit timezone-aware publication timestamp is admissible.
    # Date-only, relative ages, upload dates and upcoming premieres are not substitutes.
    published = ensure_kst(datetime.fromisoformat(meta.get("publishDate", "").replace("Z", "+00:00")))
    if not is_recent(published, now=now):
        return None
    title = normalize_text(details.get("title", ""))
    description = normalize_text(details.get("shortDescription", ""))[:1800]
    text = normalize_text(f"{title}\n{description}")
    if not title or (filter_terms and not any(term.casefold() in text.casefold() for term in filter_terms)):
        return None
    return CollectedNotice(game_id, f"https://www.youtube.com/watch?v={video_id}",
                           title, published, now, text, content_hash(text),
                           source_type="OFFICIAL_YOUTUBE")


def collect_channel_fallback(http, source, now, *, max_videos=3):
    channel_id = source["youtube_channel_id"]
    data = channel_data(http, source["youtube"], channel_id)
    for tab in values_for(data.get("contents", {}), "tabRenderer"):
        endpoint = tab.get("endpoint", {})
        path = endpoint.get("commandMetadata", {}).get("webCommandMetadata", {}).get("url", "")
        if path.endswith("/videos") and endpoint.get("browseEndpoint", {}).get("browseId") == channel_id:
            data = channel_data(http, urljoin(source["youtube"], path), channel_id)
            break
    else:
        raise ValueError("verified video tab missing")
    ids = list(dict.fromkeys(v for v in values_for(data.get("contents", {}), "videoId")
                            if isinstance(v, str) and re.fullmatch(r"[A-Za-z0-9_-]{11}", v)))[:max_videos]
    items = []
    for video_id in ids:
        try:
            html = http.get(f"https://www.youtube.com/watch?v={video_id}").text()
            item = parse_watch(html, source["game_id"], channel_id, video_id, now,
                               tuple(source.get("youtube_filter_terms", ())))
            if item:
                items.append(item)
        except (HttpClientError, ValueError, TypeError, AttributeError):
            continue
    return tuple(items)
