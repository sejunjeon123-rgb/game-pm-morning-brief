"""Verified official-board adapters for JavaScript-rendered notice pages.

Adapters use only publisher-operated or official-homepage-linked public GET
endpoints.  They return normalized documents and leave state/change detection to
the collector.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
import json
import re
from typing import Any, Mapping
from urllib.parse import urlencode

from market_signal.normalize import extract_text
from shared.http_client import HttpClient
from shared.time_utils import KST, is_recent, now_kst


@dataclass(frozen=True, slots=True)
class OfficialDocument:
    game_id: str
    url: str
    title: str
    published_at: datetime
    normalized_text: str
    source_type: str = "OFFICIAL_COMMUNITY"


@dataclass(frozen=True, slots=True)
class AdapterSpec:
    kind: str
    values: Mapping[str, Any]


ADAPTER_SPECS: Mapping[str, AdapterSpec] = {
    "odin-valhalla-rising": AdapterSpec(
        "odin_homepage",
        {"homepage": "https://odin.kakaogames.com/odin/"},
    ),
    "lineage-m": AdapterSpec(
        "plaync_community",
        {"api_base": "https://api-community.plaync.com/lineagem/", "board_alias": "notice"},
    ),
    "nikke": AdapterSpec(
        "naver_game_lounge",
        {"lounge_id": "nikke", "board_ids": (11, 48, 130, 56, 14)},
    ),
    "epic-seven": AdapterSpec(
        "stove_community",
        {"channel_seq": 127, "board_ids": (995, 997, 999, 1000)},
    ),
    "seven-knights-rebirth": AdapterSpec(
        "netmarble_forum",
        {
            "game_code": "tskgb",
            "forum_id": "sena_rebirth",
            "menu_ids": (20, 10, 11, 12, 15),
        },
    ),
    "trickcal-revive": AdapterSpec(
        "naver_cafe",
        {"cafe_id": 30131231, "menu_ids": (66, 67, 68, 14, 15)},
    ),
}


class _OdinNewsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[tuple[str, str]] = []
        self._url = ""
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "a" and values.get("id") == "a_main_news_article":
            self._url = values.get("href") or ""
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._url:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._url:
            self.items.append((self._url, " ".join("".join(self._text).split())))
            self._url = ""
            self._text = []


def parse_odin_homepage(
    html_text: str,
    *,
    reference: datetime | None = None,
    source_url: str = "https://odin.kakaogames.com/odin/",
) -> tuple[OfficialDocument, ...]:
    parser = _OdinNewsParser()
    parser.feed(html_text)
    current = reference or now_kst()
    documents: list[OfficialDocument] = []
    for _linked_url, title in parser.items:
        match = re.search(r"(?<!\d)(\d{1,2})/(\d{1,2})", title)
        if not match:
            continue
        month, day = map(int, match.groups())
        year = current.year - 1 if month > current.month + 6 else current.year
        documents.append(
            OfficialDocument(
                game_id="odin-valhalla-rising",
                url=source_url,
                title=title,
                published_at=datetime(year, month, day, tzinfo=KST),
                normalized_text=f"오딘 공식 홈페이지 새소식: {title}",
                source_type="OFFICIAL_HOMEPAGE",
            )
        )
    return tuple(documents)


def _epoch_millis(value: object) -> datetime:
    return datetime.fromtimestamp(int(value) / 1000, tz=KST)


def _iso_datetime(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("official API timestamp must include a timezone")
    return parsed.astimezone(KST)


def _clean_html(value: object) -> str:
    text = str(value or "")
    return extract_text(unescape(text)) if "<" in text else " ".join(unescape(text).split())


def parse_netmarble_articles(payload: Mapping[str, Any], *, menu_id: int) -> tuple[OfficialDocument, ...]:
    documents: list[OfficialDocument] = []
    for article in payload.get("articleList", []):
        if not isinstance(article, Mapping) or article.get("delFlag") not in (None, 0):
            continue
        article_id = int(article["id"])
        actual_menu = int(article.get("menuSeq", menu_id))
        documents.append(
            OfficialDocument(
                game_id="seven-knights-rebirth",
                url=f"https://forum.netmarble.com/sena_rebirth/view/{actual_menu}/{article_id}",
                title=_clean_html(article.get("title")),
                published_at=_epoch_millis(article.get("regDate") or article.get("addDate")),
                normalized_text=_clean_html(article.get("content")),
            )
        )
    return tuple(item for item in documents if item.title and item.normalized_text)


def parse_naver_cafe_articles(payload: Mapping[str, Any], *, menu_id: int) -> tuple[OfficialDocument, ...]:
    result = payload.get("result", {})
    rows = result.get("articleList", []) if isinstance(result, Mapping) else []
    documents: list[OfficialDocument] = []
    for row in rows:
        article = row.get("item", {}) if isinstance(row, Mapping) else {}
        if not isinstance(article, Mapping) or article.get("blindArticle"):
            continue
        article_id = int(article["articleId"])
        actual_menu = int(article.get("menuId", menu_id))
        documents.append(
            OfficialDocument(
                game_id="trickcal-revive",
                url=(f"https://cafe.naver.com/f-e/cafes/30131231/articles/{article_id}"
                     f"?boardtype=L&menuid={actual_menu}&referrerAllArticles=false"),
                title=_clean_html(article.get("subject")),
                published_at=_epoch_millis(article.get("writeDateTimestamp")),
                normalized_text=_clean_html(article.get("summary")),
            )
        )
    return tuple(item for item in documents if item.title and item.normalized_text)


def parse_plaync_article(payload: Mapping[str, Any]) -> OfficialDocument:
    article = payload["article"]
    meta = article["contentMeta"]
    content = article["content"]
    article_id = str(meta["id"])
    return OfficialDocument(
        game_id="lineage-m",
        url=f"https://lineagem.plaync.com/board/notice/view?articleId={article_id}",
        title=_clean_html(meta.get("title")),
        published_at=_iso_datetime(meta["timestamps"]["publishedAt"]),
        normalized_text=_clean_html(content.get("content")),
        source_type="OFFICIAL_HOMEPAGE",
    )


def _naver_editor_text(serialized: object) -> str:
    document = json.loads(str(serialized or "{}"))
    parts: list[str] = []

    def visit(value: object) -> None:
        if isinstance(value, Mapping):
            if value.get("@ctype") == "textNode" and isinstance(value.get("value"), str):
                parts.append(value["value"])
            else:
                for child in value.values():
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(document)
    return " ".join("".join(parts).split())


def parse_naver_lounge_feeds(payload: Mapping[str, Any]) -> tuple[OfficialDocument, ...]:
    content = payload.get("content", {})
    rows = content.get("feeds", []) if isinstance(content, Mapping) else []
    documents: list[OfficialDocument] = []
    for row in rows:
        feed = row.get("feed", {}) if isinstance(row, Mapping) else {}
        if not isinstance(feed, Mapping):
            continue
        feed_id = int(feed["feedId"])
        published = datetime.strptime(str(feed["createdDate"]), "%Y%m%d%H%M%S").replace(tzinfo=KST)
        normalized = _naver_editor_text(feed.get("contents"))
        documents.append(
            OfficialDocument(
                game_id="nikke",
                url=f"https://game.naver.com/lounge/nikke/board/detail/{feed_id}",
                title=_clean_html(feed.get("title")),
                published_at=published,
                normalized_text=normalized,
                source_type="OFFICIAL_COMMUNITY",
            )
        )
    return tuple(item for item in documents if item.title and item.normalized_text)


def parse_stove_article(payload: Mapping[str, Any]) -> OfficialDocument:
    article = payload["value"]
    article_id = str(article["article_id"])
    return OfficialDocument(
        game_id="epic-seven",
        url=f"https://page.onstove.com/epicseven/kr/view/{article_id}",
        title=_clean_html(article.get("title")),
        published_at=_epoch_millis(article["create_datetime"]),
        normalized_text=_clean_html(article.get("content")),
        source_type="OFFICIAL_COMMUNITY",
    )


def collect_official_board(game_id: str, http: HttpClient, *, rows: int = 20) -> tuple[OfficialDocument, ...]:
    spec = ADAPTER_SPECS[game_id]
    documents: dict[str, OfficialDocument] = {}
    if spec.kind == "odin_homepage":
        html_text = http.get(str(spec.values["homepage"])).text()
        for item in parse_odin_homepage(html_text):
            documents[item.url] = item
    elif spec.kind == "plaync_community":
        api_base = str(spec.values["api_base"])
        board_alias = str(spec.values["board_alias"])
        query = urlencode({
            "isVote": "true", "moreSize": rows, "moreDirection": "BEFORE", "previousArticleId": 0,
        })
        list_url = f"{api_base}board/{board_alias}/article/search/moreArticle?{query}"
        headers = {"Referer": "https://lineagem.plaync.com/board/notice/list"}
        payload = http.get_json(list_url, headers=headers)
        for row in payload.get("contentList", []):
            article_id = str(row["id"])
            detail_url = f"{api_base}board/{board_alias}/article/{article_id}"
            detail = http.get_json(detail_url, headers={"Referer": f"https://lineagem.plaync.com/board/notice/view?articleId={article_id}"})
            item = parse_plaync_article(detail)
            documents[item.url] = item
    elif spec.kind == "naver_game_lounge":
        lounge_id = str(spec.values["lounge_id"])
        api_base = "https://comm-api.game.naver.com/nng_main/v1"
        headers = {
            "Referer": f"https://game.naver.com/lounge/{lounge_id}/board",
            "Front-Client-Product-Type": "web",
            "Front-Client-Platform-Type": "PC",
        }
        for board_id in spec.values["board_ids"]:
            query = urlencode({
                "offset": 0, "limit": rows, "order": "NEW", "boardId": board_id, "buffFilteringYN": "N",
            })
            url = f"{api_base}/community/lounge/{lounge_id}/feed?{query}"
            payload = http.get_json(url, headers=headers | {"Referer": f"https://game.naver.com/lounge/{lounge_id}/board/{board_id}"})
            for item in parse_naver_lounge_feeds(payload):
                documents[item.url] = item
    elif spec.kind == "stove_community":
        channel_seq = int(spec.values["channel_seq"])
        api_base = "https://api.onstove.com/cwms"
        headers = {
            "X-Nation": "KR", "X-Device-Type": "P01", "X-Lang": "ko",
            "X-Client-Lang": "ko", "X-Channel-Seq": str(channel_seq), "caller-id": "storee-cp",
        }
        for board_id in spec.values["board_ids"]:
            query = urlencode({"page": 1, "size": rows})
            list_url = f"{api_base}/v3.0/article_group/BOARD/{board_id}/article/list?{query}"
            referer = f"https://page.onstove.com/epicseven/kr/list/{board_id}"
            payload = http.get_json(list_url, headers=headers | {"Referer": referer})
            for row in payload.get("value", {}).get("list", []):
                published = _epoch_millis(row["create_datetime"])
                if not is_recent(published):
                    continue
                article_id = str(row["article_id"])
                detail_url = f"{api_base}/v3.0/article?{urlencode({'article_id': article_id})}"
                detail = http.get_json(detail_url, headers=headers | {"Referer": f"https://page.onstove.com/epicseven/kr/view/{article_id}"})
                item = parse_stove_article(detail)
                documents[item.url] = item
    elif spec.kind == "netmarble_forum":
        game_code = spec.values["game_code"]
        forum_id = spec.values["forum_id"]
        for menu_id in spec.values["menu_ids"]:
            query = urlencode({"rows": rows, "start": 0, "viewType": "pv", "sort": "NEW", "menuSeq": menu_id})
            url = f"https://forum.netmarble.com/api/game/{game_code}/official/forum/{forum_id}/article/list?{query}"
            payload = http.get_json(url, headers={"Referer": f"https://forum.netmarble.com/{forum_id}"})
            for item in parse_netmarble_articles(payload, menu_id=menu_id):
                documents[item.url] = item
    elif spec.kind == "naver_cafe":
        cafe_id = int(spec.values["cafe_id"])
        for menu_id in spec.values["menu_ids"]:
            query = urlencode({"page": 1, "pageSize": rows, "viewType": "L"})
            url = f"https://apis.naver.com/cafe-web/cafe-boardlist-api/v1/cafes/{cafe_id}/menus/{menu_id}/articles?{query}"
            referer = f"https://cafe.naver.com/f-e/cafes/{cafe_id}/menus/{menu_id}?viewType=L"
            payload = http.get_json(url, headers={"Referer": referer})
            for item in parse_naver_cafe_articles(payload, menu_id=menu_id):
                documents[item.url] = item
    return tuple(sorted(documents.values(), key=lambda item: item.published_at, reverse=True))
