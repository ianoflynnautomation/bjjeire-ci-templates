from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.package import (  # noqa: E402
    artifact_name,
    bundle_artifact_name,
    layout_collected,
    package_category,
    package_many,
    parse_artifact_dirname,
    parse_package_spec,
)
from lib.models import canonical_category, parse_required_categories  # noqa: E402
from lib.models import ExecutiveReport, ReportMeta, CategoryResult  # noqa: E402


class PackageTests(unittest.TestCase):
    def test_package_copies_globs_and_writes_meta(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        source = tmp / "maven"
        surefire = source / "src" / "api" / "target" / "surefire-reports"
        surefire.mkdir(parents=True)
        (surefire / "TEST-GymServiceTest.xml").write_text("<testsuite/>\n", encoding="utf-8")
        (surefire / "ignored.txt").write_text("nope\n", encoding="utf-8")
        dest = tmp / "staged" / "unit"

        result = package_category(
            category="unit",
            source_dir=source,
            destination=dest,
            globs="**/surefire-reports/*.xml",
            source="java",
            job="java_build_test",
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["files"], 1)
        self.assertEqual(result["artifact_name"], "report-unit-java")
        copied = dest / "src" / "api" / "target" / "surefire-reports" / "TEST-GymServiceTest.xml"
        self.assertTrue(copied.is_file())
        meta = json.loads((dest / "_meta.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["category"], "unit")
        self.assertEqual(meta["source"], "java")
        self.assertEqual(meta["status"], "success")

    def test_package_empty_is_skipped(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        dest = tmp / "staged" / "acceptance"
        result = package_category(
            category="api",
            source_dir=tmp / "empty",
            destination=dest,
            globs="**/*.json",
            source="cucumber",
            skip_reason="Cucumber JSON was not uploaded",
        )
        self.assertEqual(result["category"], "acceptance")
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["files"], 0)
        meta = json.loads((dest / "_meta.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["reason"], "Cucumber JSON was not uploaded")

    def test_layout_folds_source_suffixed_artifacts(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        collected = tmp / "collected"
        unit_java = collected / "report-unit-java"
        unit_java.mkdir(parents=True)
        (unit_java / "_meta.json").write_text(
            json.dumps({"category": "unit", "source": "java", "status": "success"}) + "\n",
            encoding="utf-8",
        )
        (unit_java / "TEST-A.xml").write_text("<testsuite/>\n", encoding="utf-8")
        fe = collected / "report-unit-frontend"
        fe.mkdir(parents=True)
        (fe / "_meta.json").write_text(
            json.dumps({"category": "unit", "source": "frontend", "status": "success"}) + "\n",
            encoding="utf-8",
        )
        (fe / "vitest-unit.xml").write_text("<testsuite/>\n", encoding="utf-8")
        system = collected / "report-system"
        system.mkdir(parents=True)
        (system / "playwright.json").write_text("{}\n", encoding="utf-8")

        results = tmp / "results"
        laid = layout_collected(collected, results)
        self.assertEqual(len(laid), 3)
        self.assertTrue((results / "unit" / "java" / "TEST-A.xml").is_file())
        self.assertTrue((results / "unit" / "frontend" / "vitest-unit.xml").is_file())
        self.assertTrue((results / "system" / "playwright.json").is_file())

    def test_parse_package_spec_two_and_three_fields(self) -> None:
        specs = parse_package_spec(
            """
            # comments and blanks ignored
            unit|**/surefire-reports/*.xml
            integration|java|**/failsafe-reports/*.xml
            system|playwright|**/*.json|**/*.xml
            """,
            default_source="maven",
        )
        self.assertEqual(specs[0].category, "unit")
        self.assertEqual(specs[0].source, "maven")
        self.assertEqual(specs[1].category, "integration")
        self.assertEqual(specs[1].source, "java")
        self.assertEqual(specs[2].globs, ("**/*.json", "**/*.xml"))
        self.assertEqual(bundle_artifact_name("java"), "report-bundle-java")

    def test_package_many_and_layout_bundle(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        source = tmp / "raw"
        (source / "surefire-reports").mkdir(parents=True)
        (source / "failsafe-reports").mkdir()
        (source / "surefire-reports" / "TEST-A.xml").write_text("<testsuite/>\n", encoding="utf-8")
        (source / "failsafe-reports" / "TEST-B.xml").write_text("<testsuite/>\n", encoding="utf-8")
        staged = tmp / "staged"
        result = package_many(
            packages="unit|**/surefire-reports/*.xml\nintegration|**/failsafe-reports/*.xml",
            source_dir=source,
            destination=staged,
            source="java",
            job="verify",
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["artifact_name"], "report-bundle-java")
        collected = tmp / "collected" / "report-bundle-java"
        collected.mkdir(parents=True)
        for child in staged.iterdir():
            dest = collected / child.name
            dest.mkdir()
            for path in child.rglob("*"):
                if path.is_file():
                    target = dest / path.relative_to(child)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(path.read_bytes())
        results = tmp / "results"
        laid = layout_collected(collected.parent, results)
        self.assertEqual(len(laid), 2)
        self.assertTrue((results / "unit" / "java" / "surefire-reports" / "TEST-A.xml").is_file())
        self.assertTrue((results / "integration" / "java" / "failsafe-reports" / "TEST-B.xml").is_file())

    def test_parse_artifact_dirname(self) -> None:
        self.assertEqual(parse_artifact_dirname("report-unit-java"), ("unit", "java"))
        self.assertEqual(parse_artifact_dirname("report-system"), ("system", ""))
        self.assertEqual(parse_artifact_dirname("report-api-compose"), ("acceptance", "compose"))
        self.assertEqual(canonical_category("ui"), "system")
        self.assertEqual(parse_required_categories("unit, api"), ("unit", "acceptance"))
        self.assertEqual(artifact_name("unit", "Java API"), "report-unit-java-api")

    def test_strict_missing_false_allows_pass_with_gaps(self) -> None:
        meta = ReportMeta(
            title="t",
            product="p",
            release_id="REL-20260826-abc",
            git_sha="abc",
            git_ref="refs/heads/main",
            branch="main",
            environment="CI",
            runner_host="r",
            actor="a",
            pipeline_run_id="1",
            run_url="",
            generated_at="now",
            workflow="ci-pr",
        )
        unit = CategoryResult(id="unit", title="Unit Tests", status="passed", tests=2, passed=2)
        missing = CategoryResult(id="acceptance", title="Acceptance Tests", status="missing")
        report = ExecutiveReport(
            meta=meta,
            categories=[unit, missing],
            required_ids=("unit", "acceptance"),
            strict_missing=False,
        )
        self.assertEqual(report.verdict, "PASS")
        report.strict_missing = True
        self.assertEqual(report.verdict, "FAIL")


if __name__ == "__main__":
    unittest.main()
