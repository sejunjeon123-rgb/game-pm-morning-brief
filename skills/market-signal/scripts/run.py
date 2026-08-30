"""Standalone Market Signal V1 entrypoint."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import load_project_config
from market_signal.runner import run_market_signal
from shared.json_utils import dumps
from shared.state_store import StateStore


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", type=Path, default=Path("state"))
    parser.add_argument("--output", type=Path, default=Path("output/market_signal_collection.json"))
    parser.add_argument("--games", nargs="+")
    parser.add_argument("--analyze", action="store_true")
    args = parser.parse_args()
    config = load_project_config(ROOT)
    report = run_market_signal(config, StateStore(args.state_dir), tuple(args.games) if args.games else config.game_ids, analyze=args.analyze)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(dumps(report) + "\n", encoding="utf-8")
    print(f"market signal report written to {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
