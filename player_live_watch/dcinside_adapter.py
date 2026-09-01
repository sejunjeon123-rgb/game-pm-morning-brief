"""Standard-library adapter for public DCInside gallery pages."""

from __future__ import annotations

import re
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit

from market_signal.normalize import normalize_text
from player_live_watch.models import PlayerPostCandidate
from shared.time_utils import KST


_COMMENT_COUNT = re.compile(r"\[(\d+)\]")
_INTEGER = re.compile(r"[\d,]+")
_SKIPPED_ROW_TYPES = frozenset({"icon_notice", "icon_survey", "icon_ad"})


def _classes(attrs: dict[str, str | None]) -> set[str]:
    return set((attrs.get("class") or "").split())


def _integer(value: str) -> int:
    match = _INTEGER.search(value)
    return int(match.group(0).replace(",", "")) if match else 0


def _canonical_post_url(base_url: str, href: str) -> str:
    absolute = urljoin(base_url, href)
    parts = urlsplit(absolute)
    query = parse_qs(parts.query)
    gallery_id = query.get("id", [""])[0]
    post_number = query.get("no", [""])[0]
    if parts.scheme != "https" or parts.netloc.lower() != "gall.dcinside.com":
        return ""
    if not gallery_id or not post_number.isdigit() or "/board/view/" not in parts.path:
        return ""
    return urlunsplit(("https", "gall.dcinside.com", parts.path, urlencode({"id": gallery_id, "no": post_number}), ""))


def _published_at(value: str) -> datetime:
    return datetime.strptime(value.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)


class DCListingParser(HTMLParser):
    """Extract public post metadata without reading or retaining author fields."""

    def __init__(self, game_id: str, source_id: str, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.game_id = game_id
        self.source_id = source_id
        self.base_url = base_url
        self.items: list[PlayerPostCandidate] = []
        self._row_depth = 0
        self._skip_row = False
        self._cell = ""
        self._in_title_anchor = False
        self._href = ""
        self._title_parts: list[str] = []
        self._date = ""
        self._comment_text: list[str] = []
        self._count_text: list[str] = []
        self._recommend_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = _classes(attributes)
        if tag == "tr" and {"ub-content", "us-post"}.issubset(classes):
            self._row_depth = 1
            self._skip_row = (attributes.get("data-type") or "") in _SKIPPED_ROW_TYPES
            self._cell = ""
            self._in_title_anchor = False
            self._href = ""
            self._title_parts = []
            self._date = ""
            self._comment_text = []
            self._count_text = []
            self._recommend_text = []
            return
        if not self._row_depth:
            return
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}:
            self._row_depth += 1
        if tag == "td":
            if "gall_tit" in classes:
                self._cell = "title"
            elif "gall_date" in classes:
                self._cell = "date"
                self._date = attributes.get("title") or ""
            elif "gall_count" in classes:
                self._cell = "count"
            elif "gall_recommend" in classes:
                self._cell = "recommend"
            else:
                self._cell = "ignored"
        elif tag == "a" and self._cell == "title":
            href = attributes.get("href") or ""
            if "/board/view/" in href and not self._href:
                self._href = href
                self._in_title_anchor = True
            elif "reply_numbox" in classes:
                self._in_title_anchor = False

    def handle_endtag(self, tag: str) -> None:
        if not self._row_depth:
            return
        if tag == "a":
            self._in_title_anchor = False
        if tag == "td":
            self._cell = ""
        self._row_depth -= 1
        if tag == "tr" and self._row_depth == 0:
            self._finish_row()

    def handle_data(self, data: str) -> None:
        if not self._row_depth or self._skip_row:
            return
        text = normalize_text(data)
        if not text:
            return
        if self._cell == "title":
            if self._in_title_anchor:
                self._title_parts.append(text)
            elif _COMMENT_COUNT.search(text):
                self._comment_text.append(text)
        elif self._cell == "date" and not self._date:
            self._date = text
        elif self._cell == "count":
            self._count_text.append(text)
        elif self._cell == "recommend":
            self._recommend_text.append(text)

    def _finish_row(self) -> None:
        if self._skip_row:
            return
        url = _canonical_post_url(self.base_url, self._href)
        title = normalize_text(" ".join(self._title_parts))
        try:
            published_at = _published_at(self._date)
        except ValueError:
            return
        if not url or len(title) < 2:
            return
        expected_id = parse_qs(urlsplit(self.base_url).query).get("id", [""])[0]
        actual_id = parse_qs(urlsplit(url).query).get("id", [""])[0]
        if expected_id and actual_id != expected_id:
            return
        comment_match = _COMMENT_COUNT.search(" ".join(self._comment_text))
        self.items.append(
            PlayerPostCandidate(
                game_id=self.game_id,
                source_id=self.source_id,
                url=url,
                title=title,
                published_at=published_at,
                comment_count=int(comment_match.group(1)) if comment_match else 0,
                view_count=_integer(" ".join(self._count_text)),
                recommendation_count=_integer(" ".join(self._recommend_text)),
            )
        )


class DCBodyParser(HTMLParser):
    """Extract only the public post body; writer and comment areas are out of scope."""

    VOID_TAGS = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._depth = 0
        self._ignored = 0
        self.values: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if not self._depth and "write_div" in _classes(attributes):
            self._depth = 1
        elif self._depth and tag not in self.VOID_TAGS:
            self._depth += 1
        if self._depth and tag in {"script", "style", "noscript", "svg"}:
            self._ignored += 1

    def handle_endtag(self, tag: str) -> None:
        if not self._depth:
            return
        if tag in {"script", "style", "noscript", "svg"} and self._ignored:
            self._ignored -= 1
        self._depth -= 1

    def handle_data(self, data: str) -> None:
        if self._depth and not self._ignored:
            text = normalize_text(data)
            if text:
                self.values.append(text)


def parse_listing(game_id: str, source_id: str, base_url: str, html: str) -> tuple[PlayerPostCandidate, ...]:
    parser = DCListingParser(game_id, source_id, base_url)
    parser.feed(html)
    unique = {item.url: item for item in parser.items}
    return tuple(sorted(unique.values(), key=lambda item: item.published_at, reverse=True))


def parse_body(html: str, *, max_characters: int = 12_000) -> str:
    parser = DCBodyParser()
    parser.feed(html)
    return normalize_text("\n".join(parser.values))[:max_characters]


def listing_page_url(base_url: str, page: int) -> str:
    if page <= 0:
        raise ValueError("page must be positive")
    parts = urlsplit(base_url)
    query = parse_qs(parts.query)
    query["page"] = [str(page)]
    pairs = [(key, value) for key, values in query.items() for value in values]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(pairs), ""))

