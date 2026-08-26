from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.models import make_release_id  # noqa: E402
from lib.parsers import load_category  # noqa: E402


class ParserTests(unittest.TestCase):
    def test_junit_counts_failures_and_skips(self) -> None:
        directory = Path(tempfile.mkdtemp())
        (directory / "surefire.xml").write_text(
            (ROOT / "fixtures" / "junit-sample.xml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        result = load_category("unit", directory)
        self.assertEqual(result.tests, 4)
        self.assertEqual(result.passed, 2)
        self.assertEqual(result.failed, 1)
        self.assertEqual(result.skipped, 1)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.failures[0].name, "shouldRejectUnknownCounty")

    def test_k6_metrics(self) -> None:
        directory = Path(tempfile.mkdtemp())
        (directory / "k6-summary.json").write_text(
            (ROOT / "fixtures" / "k6-summary.sample.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        result = load_category("performance", directory)
        self.assertIsNotNone(result.metrics)
        assert result.metrics is not None
        self.assertAlmostEqual(result.metrics.p95_ms or 0, 188.5)
        self.assertAlmostEqual(result.metrics.rps or 0, 24.0)
        self.assertEqual(result.metrics.error_rate, 0.0)
        self.assertEqual(result.status, "passed")

    def test_missing_directory(self) -> None:
        result = load_category("api", Path("/tmp/does-not-exist-bjjeire-report"))
        self.assertEqual(result.status, "missing")
        self.assertEqual(result.tests, 0)

    def test_playwright_stats(self) -> None:
        directory = Path(tempfile.mkdtemp())
        (directory / "playwright.json").write_text(
            (ROOT / "fixtures" / "playwright-api.sample.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        result = load_category("api", directory)
        self.assertEqual(result.tests, 24)
        self.assertEqual(result.passed, 24)
        self.assertEqual(result.status, "passed")
        self.assertGreater(result.duration_s, 0)

    def test_lighthouse_score(self) -> None:
        directory = Path(tempfile.mkdtemp())
        (directory / "lighthouse.json").write_text(
            (ROOT / "fixtures" / "lighthouse.sample.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        result = load_category("performance", directory)
        self.assertIsNotNone(result.metrics)
        assert result.metrics is not None
        self.assertAlmostEqual(result.metrics.lighthouse_performance or 0, 92.0)
        self.assertEqual(result.status, "passed")

    def test_cucumber_scenarios(self) -> None:
        directory = Path(tempfile.mkdtemp())
        (directory / "cucumber.json").write_text(
            (ROOT / "fixtures" / "cucumber.sample.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        result = load_category("acceptance", directory, source_job="acceptance")
        self.assertEqual(result.tests, 2)
        self.assertEqual(result.passed, 1)
        self.assertEqual(result.failed, 1)
        self.assertEqual(result.gate_status, "Failed")
        self.assertEqual(len(result.artifacts), 1)
        self.assertEqual(len(result.artifacts[0].sha256), 64)

    def test_missing_is_critical_gate(self) -> None:
        result = load_category("system", Path("/tmp/does-not-exist-bjjeire-report"))
        self.assertEqual(result.gate_status, "MISSING / CRITICAL FAILURE")

    def test_release_id_format(self) -> None:
        from datetime import datetime, timezone

        stamp = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
        self.assertEqual(make_release_id(stamp, "a1b2c3def"), "REL-20260825-a1b2c3d")

    def test_meta_notes_survive_empty_dir(self) -> None:
        directory = Path(tempfile.mkdtemp())
        (directory / "_meta.json").write_text(
            json.dumps({"status": "skipped", "reason": "Playwright not invoked on this release"}),
            encoding="utf-8",
        )
        result = load_category("ui", directory)
        self.assertEqual(result.status, "missing")
        self.assertTrue(any("Playwright" in note for note in result.notes))


if __name__ == "__main__":
    unittest.main()
