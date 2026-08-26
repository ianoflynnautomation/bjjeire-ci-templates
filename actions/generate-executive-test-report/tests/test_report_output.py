from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from datetime import datetime, timezone

from generate_report import main as generate  # noqa: E402
from lib.models import make_release_id  # noqa: E402
from lib.preview import stage_sample_results  # noqa: E402


def _extract_pdf_text(pdf: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise unittest.SkipTest("pypdf is required to assert PDF text") from exc
    reader = PdfReader(str(pdf))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


class ReportOutputTests(unittest.TestCase):
    def test_fixture_pack_writes_pdf_summary_and_catalog(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        results = stage_sample_results(tmp / "results")
        pdf = tmp / "report.pdf"
        summary = tmp / "summary.md"
        verdict_path = tmp / "verdict.json"

        rc = generate(
            [
                "--results-dir",
                str(results),
                "--output",
                str(pdf),
                "--summary-md",
                str(summary),
                "--verdict-json",
                str(verdict_path),
                "--environment",
                "Staging",
                "--sha",
                "a1b2c3def",
                "--branch",
                "main",
                "--actor",
                "auditor",
                "--runner-host",
                "runner-1",
                "--run-id",
                "99",
                "--run-url",
                "https://example.invalid/run/99",
            ]
        )
        self.assertEqual(rc, 0)
        self.assertTrue(pdf.is_file())
        self.assertGreater(pdf.stat().st_size, 1000)
        self.assertTrue(pdf.read_bytes().startswith(b"%PDF"))

        verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
        expected_id = make_release_id(datetime.now(timezone.utc), "a1b2c3def")
        self.assertEqual(verdict["release_id"], expected_id)
        self.assertEqual(verdict["verdict"], "FAIL")
        self.assertEqual(len(verdict["catalog"]), 6)
        for row in verdict["catalog"]:
            self.assertEqual(len(row["sha256"]), 64)
            self.assertRegex(row["sha256"], r"^[0-9a-f]{64}$")

        markdown = summary.read_text(encoding="utf-8")
        self.assertIn(expected_id, markdown)
        self.assertIn("Artifact catalog & provenance", markdown)
        self.assertIn("Compliance gate", markdown)
        self.assertIn("Staging", markdown)

        text = _extract_pdf_text(pdf)
        self.assertIn(expected_id, text)
        self.assertIn("Audit-Ready Compliance Release Report", text)
        self.assertIn("SHA-256", text)
        self.assertIn("Unit Tests", text)
        self.assertIn("Acceptance Tests", text)
        self.assertIn("System / E2E Tests", text)
        self.assertIn("Failed", text)
        self.assertIn("Passed", text)

    def test_missing_required_stages_are_critical_failures(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        pdf = tmp / "report.pdf"
        summary = tmp / "summary.md"
        verdict_path = tmp / "verdict.json"
        rc = generate(
            [
                "--results-dir",
                str(tmp / "empty-results"),
                "--output",
                str(pdf),
                "--summary-md",
                str(summary),
                "--verdict-json",
                str(verdict_path),
                "--sha",
                "deadbee",
                "--fail-on-test-failure",
            ]
        )
        self.assertEqual(rc, 2)
        verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
        self.assertEqual(verdict["verdict"], "FAIL")
        self.assertEqual(verdict["release_id"], make_release_id(datetime.now(timezone.utc), "deadbee"))
        for gate in ("unit", "integration", "acceptance", "system"):
            self.assertEqual(verdict["gates"][gate], "MISSING / CRITICAL FAILURE")
        markdown = summary.read_text(encoding="utf-8")
        self.assertIn("MISSING / CRITICAL FAILURE", markdown)
        text = _extract_pdf_text(pdf)
        self.assertIn("MISSING / CRITICAL FAILURE", text)
        self.assertIn(make_release_id(datetime.now(timezone.utc), "deadbee"), text)

    def test_no_strict_missing_does_not_fail_on_gaps(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        pdf = tmp / "report.pdf"
        verdict_path = tmp / "verdict.json"
        rc = generate(
            [
                "--results-dir",
                str(tmp / "empty-results"),
                "--output",
                str(pdf),
                "--verdict-json",
                str(verdict_path),
                "--sha",
                "deadbee",
                "--no-strict-missing",
                "--fail-on-test-failure",
            ]
        )
        self.assertEqual(rc, 0)
        verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
        self.assertEqual(verdict["verdict"], "PASS")
        self.assertFalse(verdict["strict_missing"])
        for gate in ("unit", "integration", "acceptance", "system"):
            self.assertEqual(verdict["gates"][gate], "MISSING / CRITICAL FAILURE")

    def test_preview_script_no_open(self) -> None:
        from preview_report import main as preview

        tmp = Path(tempfile.mkdtemp())
        rc = preview(["--out-dir", str(tmp), "--no-open", "--clean", "--sha", "a1b2c3def"])
        self.assertEqual(rc, 0)
        self.assertTrue((tmp / "audit-release-report.pdf").is_file())
        self.assertTrue((tmp / "summary.md").is_file())
        self.assertTrue((tmp / "verdict.json").is_file())
        self.assertTrue((tmp / "results" / "unit" / "junit-sample.xml").is_file())


if __name__ == "__main__":
    unittest.main()
