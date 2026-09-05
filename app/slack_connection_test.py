"""One-shot Slack check; no collection, AI, Notion, or state writes."""
import os

from shared.slack_client import format_connection_test, post_webhook


def main():
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL", "")
    if not webhook_url:
        raise SystemExit("Required Slack configuration is missing")
    post_webhook(webhook_url, format_connection_test())
    print("Slack connection test completed")


if __name__ == "__main__":
    main()
