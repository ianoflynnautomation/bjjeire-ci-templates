#!/usr/bin/env python3
"""Generate a fixture-based audit PDF and open it for review."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from generate_report import main as generate  # noqa: E402
from lib.preview import stage_sample_results  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    args = _parse(argv)
    out_dir: Path = args.out_dir
    results_dir = out_dir / "results"
    pdf = out_dir / "audit-release-report.pdf"
    summary = out_dir / "summary.md"
    verdict = out_dir / "verdict.json"

    if args.clean and out_dir.exists():
        import shutil

        shutil.rmtree(out_dir)

    stage_sample_results(results_dir, include_performance=not args.skip_performance)
    generate_argv = [
        "--results-dir",
        str(results_dir),
        "--output",
        str(pdf),
        "--summary-md",
        str(summary),
        "--verdict-json",
        str(verdict),
        "--title",
        "Audit-Ready Compliance Release Report",
        "--product",
        args.product,
        "--environment",
        args.environment,
        "--sha",
        args.sha,
        "--ref",
        args.ref,
        "--branch",
        args.branch,
        "--actor",
        args.actor,
        "--runner-host",
        args.runner_host,
        "--run-id",
        args.run_id,
        "--run-url",
        args.run_url,
        "--workflow",
        "preview_report",
    ]
    rc = generate(generate_argv)
    print()
    print(f"PDF      {pdf}")
    print(f"Summary  {summary}")
    print(f"Verdict  {verdict}")
    if summary.is_file():
        print()
        print("----- GitHub Step Summary -----")
        print(summary.read_text(encoding="utf-8"))
        print("----- end -----")
    if args.no_open:
        return rc
    _open_path(pdf)
    return rc


def _open_path(path: Path) -> None:
    if os.environ.get("CI"):
        print("CI=true — skipping viewer")
        return
    viewers = {
        "darwin": ["open"],
        "linux": ["xdg-open"],
        "win32": ["cmd", "/c", "start", ""],
    }
    cmd = viewers.get(sys.platform)
    if not cmd:
        print(f"Open {path} in a PDF viewer")
        return
    try:
        subprocess.run([*cmd, str(path)], check=False)
    except OSError as exc:
        print(f"Could not open {path}: {exc}")


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "out", help="Where to write results + PDF (default: ./out)")
    parser.add_argument("--no-open", action="store_true", help="Do not launch a PDF viewer")
    parser.add_argument("--clean", action="store_true", help="Delete --out-dir before generating")
    parser.add_argument("--skip-performance", action="store_true")
    parser.add_argument("--product", default="BjjEire")
    parser.add_argument("--environment", default="Staging")
    parser.add_argument("--sha", default="a1b2c3def")
    parser.add_argument("--ref", default="refs/heads/main")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--actor", default="local-preview")
    parser.add_argument("--runner-host", default="localhost")
    parser.add_argument("--run-id", default="preview")
    parser.add_argument("--run-url", default="")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
