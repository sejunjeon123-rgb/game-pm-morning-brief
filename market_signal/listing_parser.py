"""Generic official notice listing parser with per-game URL allow rules."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser

from market_signal.models import NoticeCandidate
from market_signal.normalize import canonical_url, normalize_text
from shared.time_utils import KST


_DATE = re.compile(r"(?<!\d)(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})(?!\d)")


@dataclass(frozen=True, slots=True)
class Token:
    text: str
    href: str | None


class ListingHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tokens: list[Token] = []
        self._href: str | None = None
        self._ignored = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._ignored += 1
        if tag == "a":
            self._href = dict(attrs).get("href")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._ignored:
            self._ignored -= 1
        if tag == "a":
            self._href = None

    def handle_data(self, data: str) -> None:
        if self._ignored:
            return
        text = normalize_text(data)
        if text:
            self.tokens.append(Token(text, self._href))


class NexonNoticeListingParser(HTMLParser):
    """Parse the publisher's stable ``data-threadid`` notice list markup."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[tuple[str, str, str]] = []
        self._item_depth = 0
        self._href: str | None = None
        self._anchor_depth = 0
        self._anchor_text: list[str] = []
        self._item_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "li" and attributes.get("data-threadid"):
            self._item_depth = 1
            self._href = None
            self._anchor_text = []
            self._item_text = []
            return
        if self._item_depth:
            if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "wbr"}:
                self._item_depth += 1
            href = attributes.get("href")
            if tag == "a" and href and "/News/Notice/" in href:
                self._href = href
                self._anchor_depth = self._item_depth

    def handle_endtag(self, tag: str) -> None:
        if not self._item_depth:
            return
        if tag == "a" and self._anchor_depth:
            self._anchor_depth = 0
        self._item_depth -= 1
        if tag == "li" and self._item_depth == 0 and self._href:
            self.items.append((self._href, normalize_text(" ".join(self._anchor_text)), normalize_text(" ".join(self._item_text))))

    def handle_data(self, data: str) -> None:
        if not self._item_depth:
            return
        text = normalize_text(data)
        if text:
            self._item_text.append(text)
            if self._anchor_depth:
                self._anchor_text.append(text)


def _allowed_notice(game_id: str, url: str) -> bool:
    lowered = url.lower()
    if game_id == "mabinogi-mobile":
        return "/news/notice" in lowered and ("thread" in lowered or lowered.rstrip("/").split("/")[-1].isdigit())
    if game_id == "lineage-m":
        return "/board/notice/" in lowered and ("view" in lowered or "article" in lowered)
    if game_id == "black-desert-mobile":
        return "/board/detail" in lowered and "boardno=6" in lowered and "contentno=" in lowered
    return False


def parse_listing(game_id: str, base_url: str, html: str) -> tuple[NoticeCandidate, ...]:
    parser = ListingHTMLParser()
    parser.feed(html)
    candidates: dict[str, NoticeCandidate] = {}
    if game_id == "mabinogi-mobile":
        nexon = NexonNoticeListingParser()
        nexon.feed(html)
        for href, title, item_text in nexon.items:
            match = _DATE.search(item_text)
            if not match or len(title) < 3:
                continue
            url = canonical_url(base_url, href)
            if _allowed_notice(game_id, url):
                candidates[url] = NoticeCandidate(
                    game_id,
                    url,
                    title,
                    datetime(*(int(part) for part in match.groups()), tzinfo=KST),
                )
    for index, token in enumerate(parser.tokens):
        if not token.href:
            continue
        url = canonical_url(base_url, token.href)
        if not _allowed_notice(game_id, url):
            continue
        nearby = " ".join(item.text for item in parser.tokens[index:index + 8])
        match = _DATE.search(nearby)
        if not match:
            continue
        published = datetime(*(int(part) for part in match.groups()), tzinfo=KST)
        title = token.text
        if len(title) < 3 or _DATE.fullmatch(title):
            continue
        candidates.setdefault(url, NoticeCandidate(game_id, url, title, published))
    return tuple(sorted(candidates.values(), key=lambda item: item.published_at, reverse=True))
