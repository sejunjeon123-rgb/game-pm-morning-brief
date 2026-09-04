"""User-requested four-route check. No state, secrets, analysis or delivery."""
import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from market_signal.collector import NEXON_BROWSER_USER_AGENT
from market_signal.diagnostics import response_metadata
from market_signal.listing_parser import parse_listing
from market_signal.youtube_fallback import embedded_json, values_for
from shared.http_client import HttpClient, HttpClientError
from shared.time_utils import is_recent

URLS = {
    "notice": "https://mabinogimobile.nexon.com/News/Notice",
    "events": "https://mabinogimobile.nexon.com/News/Events?headlineId=2501",
    "cafe": "https://cafe.naver.com/nicolaksn",
    "youtube": "https://www.youtube.com/@mabinogimobile_official/videos",
}


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.frames = [], []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        if tag == "iframe" and attrs.get("src"):
            self.frames.append(attrs["src"])


def inspect(http, url, kind):
    response = http.get(url, headers={"User-Agent": NEXON_BROWSER_USER_AGENT,
        "Accept-Language": "ko-KR,ko;q=0.9", "Referer": "https://mabinogimobile.nexon.com/Main"})
    html = response.text()
    row = {"route": kind, **response_metadata(response, url)}
    links = Links(); links.feed(html)
    if kind in {"homepage", "notice", "events"}:
        row["links_to_supplied_cafe"] = any(urlsplit(urljoin(response.url, x)).hostname == "cafe.naver.com"
            and urlsplit(urljoin(response.url, x)).path.rstrip("/") == "/nicolaksn" for x in links.links)
        row["event_links"] = sum("/news/events/" in x.lower() for x in links.links)
    if kind == "notice":
        items = parse_listing("mabinogi-mobile", url, html)
        row["parsed_notices"] = len(items)
        row["recent_notices"] = sum(is_recent(x.published_at) for x in items)
    if kind.startswith("cafe"):
        row["article_link_count"] = sum(bool(re.search(r"ArticleRead|/articles/|/nicolaksn/\d+", x)) for x in links.links)
        row["frame_count"] = len(links.frames)
        row["game_name_present"] = "마비노기" in html
        row["login_form_present"] = 'id="frmNIDLogin"' in html
    if kind == "youtube":
        try:
            data = embedded_json(html, "ytInitialData")
            row["channel_identity_match"] = data.get("metadata", {}).get("channelMetadataRenderer", {}).get("externalId") == "UCuvBRRZmmVF2BEHzdL3pPvA"
            row["video_ids_exposed"] = len({v for v in values_for(data.get("contents", {}), "videoId") if isinstance(v, str) and re.fullmatch(r"[A-Za-z0-9_-]{11}", v)})
            row["relative_date_fields"] = len(list(values_for(data.get("contents", {}), "publishedTimeText")))
        except (ValueError, TypeError, AttributeError):
            row["metadata_parse_gap"] = True
    print(json.dumps(row), flush=True)
    if kind == "cafe":
        for src in links.frames:
            frame = urljoin(response.url, src)
            if urlsplit(frame).scheme == "https" and urlsplit(frame).hostname == "cafe.naver.com":
                inspect(http, frame, "cafe_embedded")
                break


def main():
    http = HttpClient(timeout=15, retries=0)
    for kind, url in {"homepage": "https://mabinogimobile.nexon.com/Main", **URLS}.items():
        try:
            inspect(http, url, kind)
        except (HttpClientError, ValueError, TypeError) as exc:
            print(json.dumps({"route": kind, "error": getattr(exc, "code", type(exc).__name__)}), flush=True)


if __name__ == "__main__":
    main()
