from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from dast_security_gate import (
    CheckResult,
    _parse_json,
    _parse_json_list,
    parse_set_cookie,
    write_report,
)


class DastSecurityGateTests(unittest.TestCase):
    def test_parse_json_rejects_non_object_payloads(self) -> None:
        self.assertEqual(_parse_json('{"status":"ready"}'), {"status": "ready"})
        self.assertEqual(_parse_json("[]"), {})
        self.assertEqual(_parse_json("not-json"), {})

    def test_parse_set_cookie_keeps_security_attributes_without_secret_value(self) -> None:
        value, attributes = parse_set_cookie(
            "pd_web_refresh=synthetic-refresh; Max-Age=3600; Path=/api/v1/web/auth; HttpOnly; SameSite=Lax"
        )

        self.assertEqual(value, "synthetic-refresh")
        self.assertEqual(attributes["name"], "pd_web_refresh")
        self.assertNotIn("value", attributes)
        self.assertTrue(attributes["httponly"])
        self.assertEqual(attributes["path"], "/api/v1/web/auth")
        self.assertEqual(attributes["samesite"], "Lax")

    def test_parse_json_list_rejects_malformed_or_non_object_items(self) -> None:
        self.assertEqual(_parse_json_list('[{"id":"session-1"}]'), [{"id": "session-1"}])
        self.assertEqual(_parse_json_list('["not-an-object"]'), [])
        self.assertEqual(_parse_json_list("not-json"), [])

    def test_report_summary_counts_failed_checks_without_sensitive_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "dast-report.json"
            write_report(
                output,
                "http://127.0.0.1:8011",
                [
                    CheckResult("ready", True, 200, "ready"),
                    CheckResult("headers", False, 200, "missing header"),
                ],
            )

            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["schema_version"], 1)
            self.assertEqual(report["summary"], {"total": 2, "passed": 1, "failed": 1})
            self.assertEqual([check["name"] for check in report["checks"]], ["ready", "headers"])
            self.assertNotIn("password", output.read_text(encoding="utf-8").lower())


if __name__ == "__main__":
    unittest.main()
