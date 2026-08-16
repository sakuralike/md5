from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_SOURCE = ROOT / "apps" / "api" / "src"
if str(API_SOURCE) not in sys.path:
    sys.path.insert(0, str(API_SOURCE))

from password_detective.core.config import get_settings
from password_detective.db.database import Database
from password_detective.modules.community.search_index import rebuild_search_index


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild public community search projections."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--batch-size", type=int, default=200)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.batch_size < 1 or args.batch_size > 1_000:
        raise SystemExit("--batch-size must be between 1 and 1000")
    database = Database(get_settings())
    try:
        with database.session_factory() as db:
            result = rebuild_search_index(
                db, apply=args.apply, batch_size=args.batch_size
            )
    finally:
        database.dispose()
    print(json.dumps(result.as_dict(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
