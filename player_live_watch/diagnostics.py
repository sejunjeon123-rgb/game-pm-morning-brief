"""Eight-game bounded DCInside check, memory-only state and numeric output."""
import json
from pathlib import Path

from app.config import load_project_config
from player_live_watch.collector import collect_dcinside_posts
from shared.http_client import HttpClient


class MemoryState:
    def read(self, key, default=None):
        return default

    def write(self, key, value):
        pass


def main():
    config = load_project_config(Path(__file__).resolve().parents[1])
    report = collect_dcinside_posts(config, MemoryState(), config.game_ids,
        client=HttpClient(timeout=10, retries=0), max_listing_pages=1,
        max_details_per_game=1, detail_workers=1, minimum_interval_seconds=0.8)
    for game in config.game_ids:
        print(json.dumps({"game_id": game, **report["metrics"].get(game, {}),
                          "gap_codes": [g.get("code", "BOUNDED_COVERAGE")
                                        for g in report["coverage_gaps"] if g["game_id"] == game]}))


if __name__ == "__main__":
    main()
