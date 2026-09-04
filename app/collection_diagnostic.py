"""Run the actual compact collection once, without AI, delivery or persistent state."""
import json
from pathlib import Path

from app.config import load_project_config
from app.daily import collect_daily
from player_live_watch.diagnostics import MemoryState
from shared.json_utils import dumps


def main():
    config = load_project_config(Path(__file__).resolve().parents[1])
    collection = collect_daily(config, MemoryState(), config.game_ids)
    output = Path("output")
    output.mkdir(exist_ok=True)
    (output / "daily_collection.json").write_text(dumps(collection), encoding="utf-8")
    summary = []
    for game in config.game_ids:
        official = [x for x in collection["official"] if x["game_id"] == game]
        players = [x for x in collection["players"] if x["game_id"] == game]
        dc = [x for x in players if x["source_type"] == "PUBLIC_COMMUNITY"]
        row = {
            "game_id": game,
            "official_notices": sum(x["source_type"] != "OFFICIAL_YOUTUBE" for x in official),
            "official_videos": sum(x["source_type"] == "OFFICIAL_YOUTUBE" for x in official),
            "dc_body": sum(x["content_availability"] == "FULL_TEXT" for x in dc),
            "dc_title_only": sum(x["content_availability"] == "TITLE_ONLY" for x in dc),
            "creator_videos": sum(x["source_type"] == "PUBLIC_CREATOR_YOUTUBE" for x in players),
            "gaps": [x for x in collection["coverage_gaps"] if x["game_id"] == game],
        }
        summary.append(row)
        print(json.dumps(row, ensure_ascii=True), flush=True)
    (output / "collection_summary.json").write_text(dumps(summary), encoding="utf-8")


if __name__ == "__main__":
    main()
