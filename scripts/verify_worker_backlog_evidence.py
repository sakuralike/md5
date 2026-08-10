from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify WP4 worker backlog drill evidence."
    )
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--write-checksums", action="store_true")
    args = parser.parse_args()
    try:
        report = json.loads(args.report.read_text(encoding="utf-8-sig"))
        if report.get("schema") != "worker-backlog-drill-v1":
            raise ValueError("unexpected report schema")
        if report.get("status") != "passed":
            raise ValueError("worker backlog drill did not pass")
        if int(report.get("queue_size", 0)) < 20:
            raise ValueError("queue backlog must exercise the alert threshold")
        enqueue = report.get("checks", {}).get("enqueue", {})
        drain = report.get("checks", {}).get("drain", {})
        if enqueue.get("status") != "passed" or int(
            enqueue.get("observed_depth", 0)
        ) < int(report["queue_size"]):
            raise ValueError("enqueue evidence does not prove the backlog was visible")
        if drain.get("status") != "passed" or int(drain.get("observed_depth", -1)) != 0:
            raise ValueError("drain evidence does not prove the queue returned to zero")
        if drain.get("worker_ready") != "ready":
            raise ValueError("worker readiness evidence is missing")
        if args.write_checksums:
            checksum_path = args.report.with_name("checksums.sha256")
            checksum = hashlib.sha256(args.report.read_bytes()).hexdigest()
            checksum_path.write_text(
                f"{checksum}  {args.report.name}\n", encoding="utf-8"
            )
        print(
            json.dumps(
                {"schema": "worker-backlog-evidence-v1", "status": "passed"},
                ensure_ascii=False,
            )
        )
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"worker backlog evidence verification failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
