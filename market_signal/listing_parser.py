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
        candidates[url] = NoticeCandidate(game_id, url, title, published)
    return tuple(sorted(candidates.values(), key=lambda item: item.published_at, reverse=True))
