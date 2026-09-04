"""Read-only Mabinogi listing diagnostic: no state, AI or delivery imports."""

import json
import re
from urllib.parse import urlsplit

from market_signal.collector import NEXON_BROWSER_USER_AGENT
from shared.http_client import HttpClient, HttpClientError


def response_metadata(response, requested_url):
    html = response.text()
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    title = re.sub(r"\s+", " ", match.group(1)).strip() if match else ""
    # Never log arbitrary server text, query strings, cookies or redirect URLs.
    known_titles = {"마비노기 모바일", "공지사항 - 마비노기 모바일", "Access Denied", "서비스 점검 중"}
    lowered = html.lower()
    return {
        "status": response.status,
        "title": title if title in known_titles else "OTHER_OR_MISSING_REDACTED",
        "html_response": "<html" in lowered,
        "redirected": response.url != requested_url,
        "same_host": urlsplit(response.url).hostname == urlsplit(requested_url).hostname,
        "length": len(html), "threads": lowered.count("data-threadid"),
        "notice_links": lowered.count("/news/notice/"),
        "scripts": lowered.count("<script"),
        "access_marker": any(x in lowered for x in ("access denied", "captcha", "verify you are human")),
    }


def main():
    url = "https://mabinogimobile.nexon.com/News/Notice"
    try:
        response = HttpClient(timeout=20, retries=0).get(url, headers={
            "User-Agent": NEXON_BROWSER_USER_AGENT, "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": "https://mabinogimobile.nexon.com/Main"})
        print(json.dumps(response_metadata(response, url), ensure_ascii=True))
    except HttpClientError as exc:
        print(json.dumps({"error": exc.code}))


if __name__ == "__main__":
    main()
