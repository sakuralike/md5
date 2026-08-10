from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / "apps" / "api" / "src"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from password_detective.core.candidate_secret_rotation import rotate_candidate_secrets
from password_detective.core.candidate_secrets import build_candidate_secret_vault
from password_detective.core.config import Settings
from password_detective.db.database import Database


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rotate encrypted candidate secrets")
    parser.add_argument("--apply", action="store_true", help="Persist changes; default is dry-run")
    parser.add_argument("--target-version", help="Required active version guard")
    parser.add_argument("--source-version", action="append", default=[])
    parser.add_argument("--report", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = Settings()
    if args.target_version and args.target_version != settings.candidate_secret_key_version:
        raise SystemExit("target version must equal CANDIDATE_SECRET_KEY_VERSION")
    vault = build_candidate_secret_vault(settings)
    database = Database(settings)
    try:
        with database.session_factory() as db:
            summary = rotate_candidate_secrets(
                db,
                vault,
                dry_run=not args.apply,
                source_versions=set(args.source_version),
            )
            if args.apply:
                db.commit()
            else:
                db.rollback()
        report = {
            "schema_version": 1,
            "operation": "candidate-secret-key-rotation",
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
