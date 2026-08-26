from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable

from .models import (
    CATEGORY_TITLES,
    DIRECTORY_ALIASES,
    ArtifactRecord,
    CategoryId,
    CategoryResult,
    PerformanceMetrics,
    TestCaseResult,
)

JUNIT_SUFFIXES = {".xml"}
JSON_SUFFIXES = {".json"}


def resolve_category_dir(results_dir: Path, category_id: CategoryId) -> Path:
    for name in DIRECTORY_ALIASES.get(category_id, (category_id,)):
        path = results_dir / name
        if path.is_dir():
            return path
    return results_dir / category_id


def load_category(
    category_id: CategoryId,
    directory: Path,
    *,
    environment: str = "",
    source_job: str = "",
    run_url: str = "",
) -> CategoryResult:
    title = CATEGORY_TITLES[category_id]
    meta = _read_meta(directory / "_meta.json") if directory.is_dir() else {}
    env = str(meta.get("environment") or environment or "")
    job = str(meta.get("job") or source_job or directory.name)
    notes = _meta_notes(meta)

    if not directory.is_dir():
        return CategoryResult(
            id=category_id,
            title=title,
            status="missing",
            environment=env,
            source_job=job or category_id,
            notes=notes + [f"No results directory at {directory}"],
        )

    files = sorted(p for p in directory.rglob("*") if p.is_file() and p.name != "_meta.json")
    if not files:
        return CategoryResult(
            id=category_id,
            title=title,
            status="missing",
            environment=env,
            source_job=job,
            notes=notes or ["Directory existed but contained no result files"],
        )

    result = CategoryResult(
        id=category_id,
        title=title,
        status="passed",
        environment=env,
        source_job=job,
        notes=list(notes),
    )
    for path in files:
        try:
            _merge_file(result, path, run_url=run_url)
        except Exception as exc:  # noqa: BLE001 — one bad file must not drop the report
            result.notes.append(f"Failed to parse {path.name}: {exc}")
            result.status = "error"
            result.artifacts.append(_artifact(result, path, run_url))

    if result.failed or result.errors:
        result.status = "failed"
    elif result.tests == 0 and result.metrics is None and result.status != "error":
        result.status = "missing"
        result.notes.append("Parsed files contained no test cases or performance metrics")
    return result


def _read_meta(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"reason": f"Unreadable status file {path.name}"}
    return payload if isinstance(payload, dict) else {}


def _meta_notes(meta: dict) -> list[str]:
    notes: list[str] = []
    if meta.get("status"):
        notes.append(f"Collector status: {meta['status']}")
    if meta.get("reason"):
        notes.append(str(meta["reason"]))
    return notes


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact(result: CategoryResult, path: Path, run_url: str) -> ArtifactRecord:
    return ArtifactRecord(
        name=path.name,
        artifact_type=result.title,
        source_job=result.source_job or result.id,
        storage_path=str(path),
        sha256=_sha256(path),
        download_url=run_url,
    )


def _merge_file(result: CategoryResult, path: Path, run_url: str = "") -> None:
    suffix = path.suffix.lower()
    result.sources.append(str(path.name))
    result.artifacts.append(_artifact(result, path, run_url))
    if suffix in JUNIT_SUFFIXES:
        _merge_junit(result, path)
        return
    if suffix in JSON_SUFFIXES:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if _looks_like_cucumber(payload):
            _merge_cucumber(result, payload)
            return
        if _looks_like_k6(payload):
            _merge_k6(result, payload, path.name)
            return
        if _looks_like_lighthouse(payload):
            _merge_lighthouse(result, payload, path.name)
            return
        if _looks_like_playwright(payload):
            _merge_playwright(result, payload)
            return
        result.notes.append(f"Unrecognized JSON shape in {path.name}")
        return
    result.notes.append(f"Skipped unsupported file {path.name}")


def _merge_junit(result: CategoryResult, path: Path) -> None:
    tree = ET.parse(path)
    root = tree.getroot()
    suites: Iterable[ET.Element]
    if root.tag.endswith("testsuites"):
        suites = root.findall("testsuite") or root.iter("testsuite")
    elif root.tag.endswith("testsuite"):
        suites = [root]
    else:
        suites = root.iter("testsuite")

    for suite in suites:
        result.duration_s += _to_float(suite.attrib.get("time"))
        for case in suite.findall("testcase"):
            status: str = "passed"
            message = None
            if case.find("failure") is not None:
                status = "failed"
                failure = case.find("failure")
                message = (failure.attrib.get("message") or failure.text or "").strip()[:400]
                result.failed += 1
            elif case.find("error") is not None:
                status = "error"
                error = case.find("error")
                message = (error.attrib.get("message") or error.text or "").strip()[:400]
                result.errors += 1
            elif case.find("skipped") is not None:
                status = "skipped"
                result.skipped += 1
            else:
                result.passed += 1
            result.tests += 1
            duration = _to_float(case.attrib.get("time"))
            if status in {"failed", "error"}:
                result.failures.append(
                    TestCaseResult(
                        name=case.attrib.get("name", "unknown"),
                        classname=case.attrib.get("classname", suite.attrib.get("name", "")),
                        status=status,  # type: ignore[arg-type]
                        duration_s=duration,
                        message=message or None,
                    )
                )


def _looks_like_cucumber(payload: object) -> bool:
    if not isinstance(payload, list) or not payload:
        return False
    first = payload[0]
    return isinstance(first, dict) and ("elements" in first or first.get("keyword") in {"Feature", "feature"} or "uri" in first)


def _looks_like_playwright(payload: object) -> bool:
    return isinstance(payload, dict) and ("suites" in payload or "stats" in payload) and "config" in payload


def _looks_like_k6(payload: object) -> bool:
    return isinstance(payload, dict) and "metrics" in payload and isinstance(payload["metrics"], dict)


def _looks_like_lighthouse(payload: object) -> bool:
    return isinstance(payload, dict) and "categories" in payload and "lighthouseVersion" in payload


def _merge_cucumber(result: CategoryResult, payload: list) -> None:
    for feature in payload:
        if not isinstance(feature, dict):
            continue
        feature_name = str(feature.get("name") or feature.get("uri") or "feature")
        for element in feature.get("elements") or []:
            if not isinstance(element, dict):
                continue
            if element.get("type") not in {None, "scenario", "scenario_outline", "background"} and element.get("keyword") not in {
                "Scenario",
                "Scenario Outline",
                "Background",
                None,
            }:
                continue
            steps = element.get("steps") or []
            duration_ns = 0
            failed = False
            skipped = False
            message = None
            for step in steps:
                if not isinstance(step, dict):
                    continue
                step_result = step.get("result") if isinstance(step.get("result"), dict) else {}
                duration_ns += int(step_result.get("duration") or 0)
                status = str(step_result.get("status") or "passed")
                if status in {"failed", "undefined", "ambiguous"}:
                    failed = True
                    message = str(step_result.get("error_message") or status)[:400]
                elif status == "skipped" and not failed:
                    skipped = True
            duration_s = duration_ns / 1_000_000_000 if duration_ns > 10_000_000 else duration_ns / 1_000_000
            result.tests += 1
            result.duration_s += duration_s
            name = str(element.get("name") or "scenario")
            if failed:
                result.failed += 1
                result.failures.append(
                    TestCaseResult(name=name, classname=feature_name, status="failed", duration_s=duration_s, message=message)
                )
            elif skipped:
                result.skipped += 1
            else:
                result.passed += 1


def _merge_playwright(result: CategoryResult, payload: dict) -> None:
    stats = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}
    expected = int(stats.get("expected") or 0)
    unexpected = int(stats.get("unexpected") or 0)
    skipped = int(stats.get("skipped") or 0)
    flaky = int(stats.get("flaky") or 0)
    duration_ms = _to_float(stats.get("duration"))
    if expected or unexpected or skipped:
        result.passed += expected
        result.failed += unexpected
        result.skipped += skipped
        result.tests += expected + unexpected + skipped
        result.duration_s += duration_ms / 1000.0 if duration_ms > 20 else duration_ms
        if flaky:
            result.notes.append(f"Playwright reported {flaky} flaky test(s)")
        _collect_playwright_failures(result, payload.get("suites") or [])
        return
    _walk_playwright_suites(result, payload.get("suites") or [])


def _walk_playwright_suites(result: CategoryResult, suites: object) -> None:
    if not isinstance(suites, list):
        return
    for suite in suites:
        if not isinstance(suite, dict):
            continue
        for spec in suite.get("specs") or []:
            if not isinstance(spec, dict):
                continue
            for test in spec.get("tests") or []:
                if not isinstance(test, dict):
                    continue
                results = test.get("results") or []
                last = results[-1] if results else {}
                status = str(last.get("status") or test.get("status") or "passed")
                duration = _to_float(last.get("duration")) / 1000.0
                result.tests += 1
                result.duration_s += duration
                if status in {"failed", "timedOut", "interrupted"}:
                    result.failed += 1
                    errors = last.get("errors") or []
                    message = None
                    if errors and isinstance(errors[0], dict):
                        message = str(errors[0].get("message") or "")[:400]
                    result.failures.append(
                        TestCaseResult(
                            name=str(spec.get("title") or test.get("title") or "unknown"),
                            classname=str(suite.get("title") or ""),
                            status="failed",
                            duration_s=duration,
                            message=message,
                        )
                    )
                elif status == "skipped":
                    result.skipped += 1
                else:
                    result.passed += 1
        _walk_playwright_suites(result, suite.get("suites") or [])


def _collect_playwright_failures(result: CategoryResult, suites: object) -> None:
    # Stats path already counted totals; only harvest failure rows for the table.
    if not isinstance(suites, list):
        return
    for suite in suites:
        if not isinstance(suite, dict):
            continue
        for spec in suite.get("specs") or []:
            if not isinstance(spec, dict):
                continue
            ok = spec.get("ok", True)
            if ok:
                continue
            result.failures.append(
                TestCaseResult(
                    name=str(spec.get("title") or "failed spec"),
                    classname=str(suite.get("title") or ""),
                    status="failed",
                    duration_s=0.0,
                    message="See Playwright HTML report for details",
                )
            )
        _collect_playwright_failures(result, suite.get("suites") or [])


def _metric_values(metric: object) -> dict:
    if not isinstance(metric, dict):
        return {}
    values = metric.get("values")
    if isinstance(values, dict):
        return values
    return metric


def _merge_k6(result: CategoryResult, payload: dict, source_name: str) -> None:
    metrics = payload.get("metrics") or {}
    duration = _metric_values(metrics.get("http_req_duration"))
    reqs = _metric_values(metrics.get("http_reqs"))
    failed = _metric_values(metrics.get("http_req_failed"))
    checks = payload.get("root_group", {}).get("checks") if isinstance(payload.get("root_group"), dict) else {}
    perf = result.metrics or PerformanceMetrics(source=source_name)
    perf.source = source_name
    perf.p50_ms = _first(duration, "med", "p(50)")
    perf.p95_ms = _first(duration, "p(95)", "p95")
    perf.p99_ms = _first(duration, "p(99)", "p99")
    perf.avg_ms = _first(duration, "avg")
    perf.rps = _first(reqs, "rate")
    count = _first(reqs, "count")
    perf.http_reqs = int(count) if count is not None else perf.http_reqs
    error_rate = _first(failed, "value", "rate")
    perf.error_rate = error_rate
    if isinstance(checks, dict):
        perf.checks_passed = int(checks.get("passes") or 0)
        perf.checks_failed = int(checks.get("fails") or 0)
        result.passed += perf.checks_passed or 0
        result.failed += perf.checks_failed or 0
        result.tests += (perf.checks_passed or 0) + (perf.checks_failed or 0)
    elif error_rate is not None:
        result.tests += 1
        if error_rate > 0:
            result.failed += 1
        else:
            result.passed += 1
    result.metrics = perf
    duration_metric = _metric_values(metrics.get("iteration_duration") or metrics.get("http_req_duration"))
    max_ms = _first(duration_metric, "max")
    if max_ms:
        result.duration_s = max(result.duration_s, max_ms / 1000.0)


def _merge_lighthouse(result: CategoryResult, payload: dict, source_name: str) -> None:
    categories = payload.get("categories") or {}
    performance = categories.get("performance") if isinstance(categories, dict) else {}
    score = performance.get("score") if isinstance(performance, dict) else None
    perf = result.metrics or PerformanceMetrics(source=source_name)
    perf.source = f"{perf.source}+lighthouse" if perf.source and "lighthouse" not in perf.source else f"lighthouse:{source_name}"
    if isinstance(score, (int, float)):
        perf.lighthouse_performance = float(score) * (100.0 if score <= 1 else 1.0)
    audits = payload.get("audits") if isinstance(payload.get("audits"), dict) else {}
    ttfb = audits.get("server-response-time", {}).get("numericValue") if isinstance(audits.get("server-response-time"), dict) else None
    if isinstance(ttfb, (int, float)) and perf.avg_ms is None:
        perf.avg_ms = float(ttfb)
    result.metrics = perf
    result.tests += 1
    if perf.lighthouse_performance is not None and perf.lighthouse_performance < 50:
        result.failed += 1
    else:
        result.passed += 1


def _first(values: dict, *keys: str) -> float | None:
    for key in keys:
        if key in values and values[key] is not None:
            return _to_float(values[key])
    return None


def _to_float(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
