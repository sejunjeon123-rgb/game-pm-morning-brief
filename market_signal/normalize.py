"""Standard-library HTML text extraction, URL canonicalization, and hashing."""

from __future__ import annotations

import hashlib
import re
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit


_SPACE = re.compile(r"\s+")


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored = 0
        self._scope = 0
        self.all_text: list[str] = []
        self.scoped_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._ignored += 1
        if tag in {"main", "article"}:
            self._scope += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._ignored:
            self._ignored -= 1
        if tag in {"main", "article"} and self._scope:
            self._scope -= 1

    def handle_data(self, data: str) -> None:
        if self._ignored:
            return
        text = normalize_text(data)
        if not text:
            return
        self.all_text.append(text)
        if self._scope:
            self.scoped_text.append(text)


def normalize_text(value: str) -> str:
    return _SPACE.sub(" ", value).strip()


def extract_text(html: str) -> str:
    parser = TextExtractor()
    parser.feed(html)
    values = parser.scoped_text or parser.all_text
    return normalize_text("\n".join(values))


class ClassTextExtractor(HTMLParser):
    VOID_TAGS = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"})

    def __init__(self, class_name: str) -> None:
        super().__init__(convert_charrefs=True)
        self.class_name = class_name
        self._scope_depth = 0
        self._ignored = 0
        self.values: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if self._scope_depth and tag not in self.VOID_TAGS:
            self._scope_depth += 1
        elif self.class_name in classes:
            self._scope_depth = 1
        if tag in {"script", "style", "noscript", "svg"}:
            self._ignored += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._ignored:
            self._ignored -= 1
        if self._scope_depth:
            self._scope_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._scope_depth and not self._ignored:
            text = normalize_text(data)
            if text:
                self.values.append(text)


def extract_text_from_class(html: str, class_name: str) -> str:
    parser = ClassTextExtractor(class_name)
    parser.feed(html)
    return normalize_text("\n".join(parser.values))


def content_hash(value: str) -> str:
    return hashlib.sha256(normalize_text(value).encode("utf-8")).hexdigest()


def canonical_url(base_url: str, href: str) -> str:
    absolute = urljoin(base_url, href)
    parts = urlsplit(absolute)
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
    ]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, urlencode(query), ""))
