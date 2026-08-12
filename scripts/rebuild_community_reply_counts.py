from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / "apps" / "api" / "src"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from password_detective.core.config import Settings
from password_detective.db.database import Database
from password_detective.modules.community.projection import (
    rebuild_reply_count_projection,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit or rebuild community post public reply-count projections"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist projection repairs; default is dry-run",
    )
    parser.add_argument("--report", type=Path, help="Optional JSON report path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = Settings()
    database = Database(settings)
    try:
        with database.session_factory() as db:
            summary = rebuild_reply_count_projection(db, apply=args.apply)
            if args.apply:
                db.commit()
            else:
                db.rollback()
        report = {
            "schema_version": 1,
            "operation": "community-reply-count-projection-rebuild",
            "status": "applied" if args.apply else "dry-run",
            **summary.as_dict(),
        }
        rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
        if args.report:
            report_path = args.report if args.report.is_absolute() else ROOT / args.report
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
        return 0
    finally:
        database.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
