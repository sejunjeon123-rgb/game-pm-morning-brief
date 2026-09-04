"""User-selected creator metadata: never official facts or inferred transcripts."""
from dataclasses import asdict
from xml.etree import ElementTree

from market_signal.youtube_collector import _parse_feed, YT
from market_signal.youtube_fallback import collect_channel_fallback
from shared.http_client import HttpClient, HttpClientError
from shared.time_utils import now_kst


def creator_sources(config, game):
    return [s for g in config.player_live_sources if g["game_id"] == game
            for s in g["sources"] if s.get("source_type") == "PUBLIC_CREATOR_YOUTUBE"
            and s.get("status") == "VERIFIED" and s.get("collection_status") == "RSS_READY"][:2]


def collect_creator_youtube(config, game_ids, *, client=None, now=None):
    http = client or HttpClient(timeout=10, retries=0)
    now = now or now_kst()
    evidence, gaps = [], []
    for game in game_ids:
        for source in creator_sources(config, game):
            channel = source["youtube_channel_id"]
            try:
                xml = http.get(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel}").text()
                if ElementTree.fromstring(xml).findtext(f"{{{YT}}}channelId") != channel:
                    raise ValueError("feed channel mismatch")
                items = _parse_feed(game, xml, now, tuple(source["game_filter_terms"]))
            except (HttpClientError, ElementTree.ParseError, ValueError):
                gaps.append({"game_id": game, "source": source["source_id"],
                             "code": "CREATOR_RSS_GAP", "reason": "creator RSS unavailable or invalid; bounded HTML fallback attempted"})
                try:
                    items = collect_channel_fallback(http, {
                        "game_id": game, "youtube": source["url"], "youtube_channel_id": channel,
                        "youtube_filter_terms": source["game_filter_terms"]}, now, max_videos=1)
                except (HttpClientError, ValueError, KeyError, TypeError, AttributeError):
                    items = ()
            for item in sorted(items, key=lambda x: x.published_at, reverse=True)[:1]:
                evidence.append(asdict(item) | {
                    "source_id": source["source_id"], "source_type": "PUBLIC_CREATOR_YOUTUBE",
                    "classification": "CREATOR_ANALYSIS", "evidence_role": "CREATOR_ANALYSIS",
                    "content_availability": "TITLE_DESCRIPTION_ONLY", "platform": "YouTube",
                    "source_host": "www.youtube.com", "caption_status": "NOT_COLLECTED",
                })
            gaps.append({"game_id": game, "source": source["source_id"],
                         "code": "CREATOR_METADATA_ONLY" if items else "CREATOR_NO_VERIFIED_RECENT",
                         "reason": "one recent game-matched title/description per channel at most; transcripts not collected; creator opinion is not population sentiment"})
    return {"evidence": evidence, "coverage_gaps": gaps}
