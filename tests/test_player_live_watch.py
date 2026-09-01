from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from app.config import load_project_config
from player_live_watch.collector import collect_dcinside_posts
from player_live_watch.dcinside_adapter import listing_page_url, parse_body, parse_listing
from shared.http_client import HttpResponse
from shared.state_store import StateStore
from shared.time_utils import KST


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


class DCInsideAdapterTests(unittest.TestCase):
    def test_listing_omits_notice_wrong_gallery_and_writer(self) -> None:
        html = (FIXTURES / "dcinside_listing.html").read_text(encoding="utf-8")
        base = "https://gall.dcinside.com/mgallery/board/lists/?id=mabinogimobile"
        items = parse_listing("mabinogi-mobile", "mabinogi-mobile-dcinside", base, html)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "업데이트 후 전투가 멈추는 현상")
        self.assertEqual(items[0].comment_count, 7)
        self.assertEqual(items[0].view_count, 1234)
        self.assertEqual(items[0].recommendation_count, 12)
        self.assertNotIn("private-writer", repr(items[0]))
        self.assertEqual(
            items[0].url,
            "https://gall.dcinside.com/mgallery/board/view/?id=mabinogimobile&no=101",
        )

    def test_body_extracts_only_write_div(self) -> None:
        html = (FIXTURES / "dcinside_detail.html").read_text(encoding="utf-8")
        body = parse_body(html)
        self.assertIn("전투 진입 시 멈춤 현상", body)
        self.assertNotIn("private-writer", body)
        self.assertNotIn("댓글 작성자", body)
        self.assertNotIn("ignore-this", body)

    def test_listing_page_url_preserves_gallery_id(self) -> None:
        value = listing_page_url(
            "https://gall.dcinside.com/mgallery/board/lists/?id=mabinogimobile",
            2,
        )
        self.assertIn("id=mabinogimobile", value)
        self.assertIn("page=2", value)

    def test_collector_writes_privacy_minimized_post(self) -> None:
        listing = (FIXTURES / "dcinside_listing.html").read_bytes()
        detail = (FIXTURES / "dcinside_detail.html").read_bytes()

        class FixtureClient:
            listing_attempts = 0

            def get(self, url: str, *, headers: object = None) -> HttpResponse:
                if "/board/lists/" in url:
                    if "page=2" in url:
                        body = b"<html></html>"
                    else:
                        self.listing_attempts += 1
                        body = b"<html><body>temporary shell</body></html>" if self.listing_attempts == 1 else listing
                    return HttpResponse(url, 200, {"Content-Type": "text/html; charset=utf-8"}, body)
                return HttpResponse(url, 200, {"Content-Type": "text/html; charset=utf-8"}, detail)

        config = load_project_config(ROOT)
        with tempfile.TemporaryDirectory() as directory:
            report = collect_dcinside_posts(
                config,
                StateStore(Path(directory)),
                ("mabinogi-mobile",),
                client=FixtureClient(),  # type: ignore[arg-type]
                max_listing_pages=2,
                max_details_per_game=5,
                detail_workers=1,
                collected_at=datetime(2026, 9, 1, 8, 10, tzinfo=KST),
            )
        self.assertEqual(len(report["posts"]), 1)
        self.assertEqual(report["coverage_gaps"], [])
        self.assertEqual(report["posts"][0]["source_type"], "PUBLIC_COMMUNITY")
        self.assertEqual(report["posts"][0]["content_availability"], "FULL_TEXT")
        self.assertEqual(report["metrics"]["mabinogi-mobile"]["semantic_retry_count"], 2)
        self.assertNotIn("private-writer", str(report))


if __name__ == "__main__":
    unittest.main()
