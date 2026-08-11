from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from assemble_staging_stability_session import load_json, validate_session, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a WP4 Staging stability session source.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--write-checksums", action="store_true")
    args = parser.parse_args()
    try:
        report = validate_session(load_json(args.input), load_json(args.profile))
        if args.output is not None:
            write_json(args.output, report)
            if args.write_checksums:
                checksum_path = args.output.with_suffix(args.output.suffix + ".sha256")
                digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
                checksum_path.write_text(f"{digest}  {args.output.name}\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"staging stability session verification failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
