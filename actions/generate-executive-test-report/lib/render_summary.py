from __future__ import annotations

from pathlib import Path

from .models import ExecutiveReport


def write_github_summary(report: ExecutiveReport, path: Path) -> None:
    rate = f"{report.pass_rate:.1f}%" if report.pass_rate is not None else "n/a"
    lines = [
        f"# {report.meta.title}",
        "",
        f"**{report.verdict}** · `{report.meta.release_id}` · {report.meta.product} · `{report.meta.environment}`",
        "",
        "## Release identification",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Release ID | `{report.meta.release_id}` |",
        f"| Target environment | {report.meta.environment} |",
        f"| Branch | `{report.meta.branch}` |",
        f"| Git SHA | `{report.meta.git_sha[:12]}` |",
        f"| Triggered by | `{report.meta.actor}` |",
        f"| CI runner host | `{report.meta.runner_host}` |",
        f"| Pipeline run ID | `{report.meta.pipeline_run_id}` |",
        f"| Timestamp (UTC) | {report.meta.generated_at} |",
        "",
        "## Totals",
        "",
        "| Tests | Passed | Failed | Skipped | Pass rate | Duration (s) |",
        "| ---: | ---: | ---: | ---: | ---: | ---: |",
        f"| {report.tests} | {report.passed} | {report.failed} | {report.skipped} | {rate} | {report.duration_s:.1f} |",
        "",
        "## Breakdown matrix",
        "",
        "| Stage / Test type | Environment | Total | Passed | Failed | Skipped | Pass rate (%) | Duration (s) | Compliance gate |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for category in report.required:
        cat_rate = f"{category.pass_rate:.1f}" if category.pass_rate is not None else "—"
        lines.append(
            f"| {category.title} | {category.environment or report.meta.environment} | {category.tests} | "
            f"{category.passed} | {category.failed + category.errors} | {category.skipped} | {cat_rate} | "
            f"{category.duration_s:.1f} | `{category.gate_status}` |"
        )
    lines += ["", "## Artifact catalog & provenance", ""]
    if not report.catalog:
        lines.append("_No input artifacts. Required gates are `MISSING / CRITICAL FAILURE`._")
    else:
        lines += [
            "| Artifact name | Type | Source job/stage | SHA-256 |",
            "| --- | --- | --- | --- |",
        ]
        for record in report.catalog:
            lines.append(f"| `{record.name}` | {record.artifact_type} | `{record.source_job}` | `{record.sha256}` |")
    lines += ["", "## Failures", ""]
    failures = [(c.title, f) for c in report.categories for f in c.failures[:20]]
    if not failures:
        lines.append("_No failing test cases in parsed artifacts._")
    else:
        lines += ["| Stage | Case | Detail |", "| --- | --- | --- |"]
        for title, case in failures:
            detail = (case.message or case.status).replace("\n", " ")[:180]
            lines.append(f"| {title} | `{case.classname}.{case.name}` | {detail} |")
    if report.meta.run_url:
        lines += ["", f"[Pipeline run]({report.meta.run_url})"]
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    path.write_text(existing + "\n".join(lines) + "\n", encoding="utf-8")
