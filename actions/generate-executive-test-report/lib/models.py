from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

CategoryId = Literal["unit", "integration", "acceptance", "system", "performance", "api", "ui"]
RunStatus = Literal["passed", "failed", "missing", "error"]
CaseStatus = Literal["passed", "failed", "skipped", "error"]
GateStatus = Literal["Passed", "Failed", "MISSING / CRITICAL FAILURE"]

REQUIRED_GATES: tuple[CategoryId, ...] = ("unit", "integration", "acceptance", "system")
CATEGORY_ORDER: tuple[CategoryId, ...] = REQUIRED_GATES + ("performance",)

CATEGORY_TITLES: dict[CategoryId, str] = {
    "unit": "Unit Tests",
    "integration": "Integration Tests",
    "acceptance": "Acceptance Tests",
    "system": "System / E2E Tests",
    "performance": "Performance Tests",
    "api": "Acceptance Tests",
    "ui": "System / E2E Tests",
}

CATEGORY_ALIASES: dict[str, CategoryId] = {
    "api": "acceptance",
    "ui": "system",
}

DIRECTORY_ALIASES: dict[CategoryId, tuple[str, ...]] = {
    "acceptance": ("acceptance", "api"),
    "system": ("system", "ui"),
}


def canonical_category(raw: str) -> CategoryId:
    key = (raw or "").strip().lower()
    mapped = CATEGORY_ALIASES.get(key, key)
    if mapped not in CATEGORY_ORDER:
        allowed = ", ".join(CATEGORY_ORDER)
        raise ValueError(f"Unknown category {raw!r}; expected one of: {allowed}")
    return mapped  # type: ignore[return-value]


def parse_required_categories(raw: str | None) -> tuple[CategoryId, ...]:
    text = (raw or "").strip()
    if not text:
        return REQUIRED_GATES
    seen: list[CategoryId] = []
    for part in text.replace(";", ",").split(","):
        item = part.strip()
        if not item:
            continue
        category = canonical_category(item)
        if category not in seen:
            seen.append(category)
    if not seen:
        return REQUIRED_GATES
    return tuple(seen)


def make_release_id(generated_at: datetime, git_sha: str) -> str:
    short = git_sha.strip()[:7] if git_sha and git_sha not in {"unknown", ""} else "unknown"
    return f"REL-{generated_at.astimezone(timezone.utc).strftime('%Y%m%d')}-{short}"


@dataclass(frozen=True)
class TestCaseResult:
    name: str
    classname: str
    status: CaseStatus
    duration_s: float
    message: str | None = None


@dataclass
class PerformanceMetrics:
    p50_ms: float | None = None
    p95_ms: float | None = None
    p99_ms: float | None = None
    avg_ms: float | None = None
    rps: float | None = None
    error_rate: float | None = None
    http_reqs: int | None = None
    checks_passed: int | None = None
    checks_failed: int | None = None
    lighthouse_performance: float | None = None
    source: str = "k6"


@dataclass(frozen=True)
class ArtifactRecord:
    name: str
    artifact_type: str
    source_job: str
    storage_path: str
    sha256: str
    download_url: str


@dataclass
class CategoryResult:
    id: CategoryId
    title: str
    status: RunStatus
    environment: str = ""
    source_job: str = ""
    tests: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    duration_s: float = 0.0
    failures: list[TestCaseResult] = field(default_factory=list)
    metrics: PerformanceMetrics | None = None
    notes: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    artifacts: list[ArtifactRecord] = field(default_factory=list)

    @property
    def pass_rate(self) -> float | None:
        if self.tests <= 0:
            return None
        return 100.0 * self.passed / self.tests

    @property
    def gate_status(self) -> GateStatus:
        if self.status == "passed":
            return "Passed"
        if self.status == "missing":
            return "MISSING / CRITICAL FAILURE"
        return "Failed"


@dataclass
class ReportMeta:
    title: str
    product: str
    release_id: str
    git_sha: str
    git_ref: str
    branch: str
    environment: str
    runner_host: str
    actor: str
    pipeline_run_id: str
    run_url: str
    generated_at: str
    workflow: str


@dataclass
class ExecutiveReport:
    meta: ReportMeta
    categories: list[CategoryResult]
    required_ids: tuple[CategoryId, ...] = REQUIRED_GATES
    strict_missing: bool = True

    @property
    def required(self) -> list[CategoryResult]:
        return [c for c in self.categories if c.id in self.required_ids]

    @property
    def tests(self) -> int:
        return sum(c.tests for c in self.required)

    @property
    def passed(self) -> int:
        return sum(c.passed for c in self.required)

    @property
    def failed(self) -> int:
        return sum(c.failed + c.errors for c in self.required)

    @property
    def skipped(self) -> int:
        return sum(c.skipped for c in self.required)

    @property
    def duration_s(self) -> float:
        return sum(c.duration_s for c in self.required)

    @property
    def pass_rate(self) -> float | None:
        if self.tests <= 0:
            return None
        return 100.0 * self.passed / self.tests

    @property
    def catalog(self) -> list[ArtifactRecord]:
        rows: list[ArtifactRecord] = []
        for category in self.categories:
            rows.extend(category.artifacts)
        return rows

    @property
    def verdict(self) -> Literal["PASS", "FAIL"]:
        for category in self.required:
            if category.status == "missing" and not self.strict_missing:
                continue
            if category.gate_status != "Passed":
                return "FAIL"
        return "PASS"
