from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"

STAGE_FILES: tuple[tuple[str, str], ...] = (
    ("unit", "junit-sample.xml"),
    ("integration", "junit-sample.xml"),
    ("acceptance", "cucumber.sample.json"),
    ("system", "playwright-ui.sample.json"),
    ("performance", "k6-summary.sample.json"),
)


def stage_sample_results(dest: Path, *, include_performance: bool = True) -> Path:
    """Copy bundled fixtures into a results tree for local preview and tests."""
    dest.mkdir(parents=True, exist_ok=True)
    for stage, filename in STAGE_FILES:
        if stage == "performance" and not include_performance:
            continue
        stage_dir = dest / stage
        stage_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(FIXTURES / filename, stage_dir / filename)
        if stage == "performance":
            shutil.copy2(FIXTURES / "lighthouse.sample.json", stage_dir / "lighthouse.sample.json")
    return dest
