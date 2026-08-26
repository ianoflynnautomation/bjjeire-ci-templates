#!/usr/bin/env python3
"""Build an audit-ready compliance release report (PDF + GitHub Step Summary)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from lib.models import (
    REQUIRED_GATES,
    ExecutiveReport,
    ReportMeta,
    make_release_id,
    parse_required_categories,
)
from lib.parsers import load_category, resolve_category_dir
from lib.render_pdf import write_pdf
from lib.render_summary import write_github_summary


def main(argv: list[str] | None = None) -> int:
    args = _parse(argv)
    generated_at = datetime.now(timezone.utc)
    sha = args.sha
    release_id = make_release_id(generated_at, sha)
    categories = []
    for category_id in REQUIRED_GATES + ("performance",):
        directory = resolve_category_dir(args.results_dir, category_id)
        if category_id == "performance" and not directory.is_dir():
            continue
        categories.append(
            load_category(
                category_id,
                directory,
                environment=args.environment,
                source_job=category_id,
                run_url=args.run_url,
            )
        )
    report = ExecutiveReport(
        meta=ReportMeta(
            title=args.title,
            product=args.product,
            release_id=release_id,
            git_sha=sha,
            git_ref=args.ref,
            branch=args.branch,
            environment=args.environment,
            runner_host=args.runner_host,
            actor=args.actor,
            pipeline_run_id=args.run_id,
            run_url=args.run_url,
            generated_at=generated_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
            workflow=args.workflow,
        ),
        categories=categories,
        required_ids=parse_required_categories(args.required_categories),
        strict_missing=not args.no_strict_missing,
    )
    write_pdf(report, args.output)
    if args.summary_md:
        write_github_summary(report, args.summary_md)
    if args.verdict_json:
        args.verdict_json.parent.mkdir(parents=True, exist_ok=True)
        args.verdict_json.write_text(
            json.dumps(
                {
                    "release_id": report.meta.release_id,
                    "verdict": report.verdict,
                    "tests": report.tests,
                    "passed": report.passed,
                    "failed": report.failed,
                    "skipped": report.skipped,
                    "pass_rate": report.pass_rate,
                    "gates": {c.id: c.gate_status for c in report.required},
                    "required_ids": list(report.required_ids),
                    "strict_missing": report.strict_missing,
                    "catalog": [record.__dict__ for record in report.catalog],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    print(
        f"Wrote {args.output} release_id={release_id} verdict={report.verdict} "
        f"tests={report.tests} failed={report.failed}"
    )
    if args.fail_on_test_failure and report.verdict == "FAIL":
        return 2
    return 0


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=Path("results"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/audit-release-report.pdf"))
    parser.add_argument("--summary-md", type=Path, default=None)
    parser.add_argument("--verdict-json", type=Path, default=None)
    parser.add_argument("--title", default="Audit-Ready Compliance Release Report")
    parser.add_argument("--product", default="Application")
    parser.add_argument("--sha", default=os.environ.get("GITHUB_SHA", "unknown"))
    parser.add_argument("--ref", default=os.environ.get("GITHUB_REF", "unknown"))
    parser.add_argument("--branch", default=os.environ.get("GITHUB_REF_NAME", "unknown"))
    parser.add_argument("--environment", default=os.environ.get("AUDIT_ENVIRONMENT", "CI"))
    parser.add_argument("--runner-host", default=os.environ.get("RUNNER_NAME") or os.environ.get("HOSTNAME", "unknown"))
    parser.add_argument("--actor", default=os.environ.get("GITHUB_ACTOR", "unknown"))
    parser.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", "unknown"))
    parser.add_argument("--run-url", default="")
    parser.add_argument("--workflow", default=os.environ.get("GITHUB_WORKFLOW", "audit-release"))
    parser.add_argument(
        "--required-categories",
        default="unit,integration,acceptance,system",
        help="Comma-separated gates that must Pass (missing is FAIL unless --no-strict-missing)",
    )
    parser.add_argument(
        "--no-strict-missing",
        action="store_true",
        help="Do not fail the verdict when a required gate is missing (PR/main path-filtered runs)",
    )
    parser.add_argument("--fail-on-test-failure", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
