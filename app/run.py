"""Command-line entrypoint for preview, test, and automatic runs."""

from __future__ import annotations

import argparse
import hashlib
import os
import json
import sys
from pathlib import Path

from app.config import load_project_config
from app.pipeline import brief_as_dict, build_preview_brief
from app.daily import build_daily, collect_daily
from shared.openai_client import OpenAIResponsesClient
from market_signal.runner import analyze_collection_file, run_market_signal
from player_live_watch.common_collector import collect_player_live_evidence
from player_live_watch.runner import analyze_player_live_collection_file
from pm_decision_lead.runner import build_morning_brief_from_files
from shared.json_utils import dumps
from shared.notion_client import NotionDeliveryError, create_page, format_notion_page
from shared.slack_client import SlackDeliveryError, format_brief, post_webhook
from shared.state_store import StateStore


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GAME PM Morning Brief runtime")
    parser.add_argument(
        "--mode",
        choices=(
            "preview",
            "collect",
            "player-live-collect",
            "player-live-analyze",
            "pm-decision",
            "analyze-collection",
            "test",
            "automatic",
            "daily",
            "daily-saved",
        ),
        default="preview",
    )
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--state-dir", type=Path, default=Path("state"))
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--games", nargs="+")
    parser.add_argument("--analyze", action="store_true")
    parser.add_argument("--collection-file", type=Path, default=Path("output/market_signal_collection.json"))
    parser.add_argument(
        "--player-live-collection-file",
        type=Path,
        default=Path("output/player_live_collection.json"),
    )
    parser.add_argument("--signal-file", type=Path)
    parser.add_argument("--player-live-insight-file", type=Path, default=Path("output/player_live_insights.json"))
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    config = load_project_config(args.root.resolve())
    if args.mode == "automatic":
        if not config.runtime["delivery"].get("live_delivery_enabled", False):
            print("Live delivery is disabled; scheduled run skipped without collection or API calls")
            return 0
        if args.games:
            raise ValueError("automatic delivery requires all eight games")
        if any(not os.environ.get(name) for name in ("OPENAI_API_KEY", "OPENAI_MODEL", "SLACK_WEBHOOK_URL", "NOTION_TOKEN", "NOTION_PARENT_PAGE_ID")):
            print("Required automatic configuration is missing", file=sys.stderr)
            return 2
    if args.mode == "pm-decision":
        result = build_morning_brief_from_files(
            args.signal_file or args.collection_file.with_name("market_signal_signals.json"),
            args.player_live_insight_file,
            game_scope=config.game_ids,
        )
        args.output_dir.mkdir(parents=True, exist_ok=True)
        destination = args.output_dir / "pm_decision_report.json"
        destination.write_text(dumps(result) + "\n", encoding="utf-8")
        if result.get("decision_status") == "completed":
            brief = result["brief"]
            (args.output_dir / "morning_brief.json").write_text(dumps(brief) + "\n", encoding="utf-8")
            (args.output_dir / "slack_preview.json").write_text(
                dumps(format_brief(brief)) + "\n", encoding="utf-8"
            )
            (args.output_dir / "notion_preview.json").write_text(
                dumps(format_notion_page(brief, "00000000000000000000000000000000")) + "\n",
                encoding="utf-8",
            )
            print(f"PM decision report and delivery previews written to {args.output_dir.resolve()}")
            return 0
        print(f"PM decision is blocked: {result.get('decision_status')}", file=sys.stderr)
        return 2
    if args.mode == "analyze-collection":
        result = analyze_collection_file(args.collection_file, StateStore(args.state_dir))
        args.output_dir.mkdir(parents=True, exist_ok=True)
        destination = args.output_dir / "market_signal_signals.json"
        destination.write_text(dumps(result) + "\n", encoding="utf-8")
        print(f"signal analysis report written to {destination.resolve()}")
        return 0 if result["analysis_status"].startswith("completed") else 2
    if args.mode == "player-live-analyze":
        result = analyze_player_live_collection_file(
            args.player_live_collection_file,
            state=StateStore(args.state_dir),
            signal_file=args.signal_file,
        )
        args.output_dir.mkdir(parents=True, exist_ok=True)
        destination = args.output_dir / "player_live_insights.json"
        destination.write_text(dumps(result) + "\n", encoding="utf-8")
        print(f"Player Live insight report written to {destination.resolve()}")
        return 0 if result["analysis_status"].startswith("completed") else 2
    if args.mode == "collect":
        report = run_market_signal(
            config,
            StateStore(args.state_dir),
            tuple(args.games) if args.games else config.game_ids,
            analyze=args.analyze,
        )
        args.output_dir.mkdir(parents=True, exist_ok=True)
        destination = args.output_dir / "market_signal_collection.json"
        destination.write_text(dumps(report) + "\n", encoding="utf-8")
        print(f"collection report written to {destination.resolve()}")
        return 0
    if args.mode == "player-live-collect":
        report = collect_player_live_evidence(
            config,
            StateStore(args.state_dir),
            tuple(args.games) if args.games else config.game_ids,
        )
        args.output_dir.mkdir(parents=True, exist_ok=True)
        destination = args.output_dir / "player_live_collection.json"
        destination.write_text(dumps(report) + "\n", encoding="utf-8")
        print(f"Player Live collection report written to {destination.resolve()}")
        return 0
    if args.mode in {"daily", "daily-saved", "automatic"}:
        state = StateStore(args.state_dir)
        games = tuple(args.games) if args.games else config.game_ids
        if not set(games) <= set(config.game_ids):
            raise ValueError("unknown game ID")
        if args.mode == "daily-saved":
            collection = json.loads(args.collection_file.read_text(encoding="utf-8"))
        else:
            collection = collect_daily(config, state, games)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "daily_collection.json").write_text(dumps(collection) + "\n", encoding="utf-8")
        limits = config.runtime["daily"]
        key, model = os.environ.get("OPENAI_API_KEY"), os.environ.get("OPENAI_MODEL")
        client = OpenAIResponsesClient(key, model, timeout=limits["api_timeout_seconds"], retries=0,
                                       max_output_tokens=limits["max_output_tokens"],
                                       reasoning_effort=limits["reasoning_effort"]) if key and model else None
        result = build_daily(config, state, collection, client)
        brief = result["brief"]
        (args.output_dir / "daily_report.json").write_text(dumps(result) + "\n", encoding="utf-8")
    else:
        brief = brief_as_dict(build_preview_brief(config))
    payload = format_brief(brief)
    notion_preview = format_notion_page(brief, "00000000000000000000000000000000")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "morning_brief.json").write_text(dumps(brief) + "\n", encoding="utf-8")
    (args.output_dir / "slack_preview.json").write_text(dumps(payload) + "\n", encoding="utf-8")
    (args.output_dir / "notion_preview.json").write_text(dumps(notion_preview) + "\n", encoding="utf-8")

    if args.mode in {"preview", "test", "daily", "daily-saved"}:
        print(f"preview written to {args.output_dir.resolve()}")
        return 0

    if args.mode == "automatic" and not config.runtime["delivery"].get("live_delivery_enabled", False):
        print(
            "automatic delivery is fail-closed until live collectors pass validation",
            file=sys.stderr,
        )
        return 3

    webhook_url = os.environ.get("SLACK_WEBHOOK_URL", "")
    notion_token = os.environ.get("NOTION_TOKEN", "")
    notion_parent_page_id = os.environ.get("NOTION_PARENT_PAGE_ID", "")
    missing = [
        name
        for name, value in (
            ("SLACK_WEBHOOK_URL", webhook_url),
            ("NOTION_TOKEN", notion_token),
            ("NOTION_PARENT_PAGE_ID", notion_parent_page_id),
        )
        if not value
    ]
    if missing:
        print(f"required delivery configuration is missing: {', '.join(missing)}", file=sys.stderr)
        return 2

    rendered_brief = dumps(brief, indent=None)
    # A rerun's generated_at changes; it must not cause a second daily delivery.
    brief_fingerprint = str(brief["brief_date_kst"])
    state = StateStore(args.state_dir)
    notion_delivery_id = hashlib.sha256(f"notion|{brief_fingerprint}".encode("utf-8")).hexdigest()
    slack_delivery_id = hashlib.sha256(f"slack|게임-사업pm-브리핑|{brief_fingerprint}".encode("utf-8")).hexdigest()
    notion_ledger = state.read("delivery/notion_sent_briefs", {"records": {}})
    slack_ledger = state.read("delivery/slack_sent_briefs", {"delivery_ids": []})
    notion_records = dict(notion_ledger.get("records", {}))
    slack_sent_ids = set(slack_ledger.get("delivery_ids", []))
    errors: list[str] = []

    pending_key = f"delivery/pending-{brief_fingerprint}"
    pending = state.read(pending_key, {"destinations": []})
    if pending["destinations"]:
        print("Delivery outcome uncertain; manual verification required before retry", file=sys.stderr)
        return 4

    notion_url = notion_records.get(notion_delivery_id, {}).get("page_url")
    if notion_url:
        print("Notion delivery skipped: idempotency record already exists")
    else:
        try:
            state.write(pending_key, {"destinations": ["notion"]})
            notion_payload = format_notion_page(brief, notion_parent_page_id)
            result = create_page(notion_token, notion_payload, retries=0)
            notion_url = result["page_url"]
            notion_records[notion_delivery_id] = result | {"brief_date_kst": str(brief["brief_date_kst"])}
            state.write("delivery/notion_sent_briefs", {"records": notion_records})
            state.write(pending_key, {"destinations": []})
            print("Notion delivery completed")
        except NotionDeliveryError as exc:
            print("Notion delivery not confirmed; Slack held for recovery", file=sys.stderr)
            return 4

    if slack_delivery_id in slack_sent_ids:
        print("Slack delivery skipped: idempotency record already exists")
    else:
        try:
            state.write(pending_key, {"destinations": ["slack"]})
            post_webhook(webhook_url, format_brief(brief, notion_url=notion_url))
            slack_sent_ids.add(slack_delivery_id)
            state.write("delivery/slack_sent_briefs", {"delivery_ids": sorted(slack_sent_ids)})
            state.write(pending_key, {"destinations": []})
            print("Slack delivery completed")
        except SlackDeliveryError as exc:
            errors.append("Slack delivery not confirmed; manual verification required")

    if errors:
        print("; ".join(errors), file=sys.stderr)
        return 4
    state.write(
        "runs/latest_success",
        {
            "brief_date_kst": brief["brief_date_kst"],
            "generated_at": brief["generated_at"],
            "mode": args.mode,
            "destinations": ["slack", "notion"],
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
