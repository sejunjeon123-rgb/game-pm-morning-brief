"""One-shot Notion connection check; no collection, AI, Slack, or state writes."""
import os

from shared.notion_client import create_page, format_connection_test_page
from shared.time_utils import now_kst


def main():
    token = os.environ.get("NOTION_TOKEN", "")
    parent_page_id = os.environ.get("NOTION_PARENT_PAGE_ID", "")
    if not token or not parent_page_id:
        raise SystemExit("Required Notion configuration is missing")
    payload = format_connection_test_page(parent_page_id, now_kst().isoformat())
    result = create_page(token, payload, retries=0)
    print("Notion connection test completed")
    print(result["page_url"])


if __name__ == "__main__":
    main()
