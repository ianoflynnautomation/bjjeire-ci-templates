#!/usr/bin/env python3
"""Package live test outputs, or fold downloaded report-* artifacts into results/."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lib.package import canonical_category, layout_collected, package_category, package_many


def main(argv: list[str] | None = None) -> int:
    args = _parse(argv)
    if args.command in {"package", "package-many"}:
        if args.command == "package-many" or args.packages:
            result = package_many(
                packages=args.packages,
                source_dir=args.source_dir,
                destination=args.destination,
                source=args.source,
                job=args.job,
                skip_reason=args.skip_reason,
            )
        else:
            result = package_category(
                category=args.category,
                source_dir=args.source_dir,
                destination=args.destination,
                globs=args.globs,
                source=args.source,
                job=args.job,
                skip_reason=args.skip_reason,
            )
        print(json.dumps(result, indent=2, default=str))
        if args.github_output:
            _write_github_output(
                args.github_output,
                {
                    "category": str(result.get("category", "")),
                    "status": str(result["status"]),
                    "destination": str(result["destination"]),
                    "artifact-name": str(result["artifact_name"]),
                    "files": str(result["files"]),
                },
            )
        if result["status"] != "success" and args.fail_if_empty:
            return 1
        return 0

    laid_out = layout_collected(args.collected_dir, args.results_dir)
    print(f"Laid out {len(laid_out)} packaged suite(s) into {args.results_dir}")
    for path in laid_out:
        print(f"  {path}")
    if args.github_output:
        _write_github_output(
            args.github_output,
            {"suites": str(len(laid_out)), "results-dir": str(args.results_dir)},
        )
    return 0


def _write_github_output(path: Path, values: dict[str, str]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    package = sub.add_parser("package", help="Copy globs into a category directory and write _meta.json")
    package.add_argument("--category", required=True)
    package.add_argument("--source-dir", type=Path, default=Path("."))
    package.add_argument("--destination", type=Path, required=True)
    package.add_argument("--globs", default="")
    package.add_argument(
        "--packages",
        default="",
        help="Newline-separated category|source|glob lines (package-many)",
    )
    package.add_argument("--source", default="")
    package.add_argument("--job", default="")
    package.add_argument(
        "--skip-reason",
        default="No matching result files were found for this category",
    )
    package.add_argument("--fail-if-empty", action="store_true")
    package.add_argument("--github-output", type=Path, default=None)

    many = sub.add_parser("package-many", help="Package several category|source|glob lines into one bundle")
    many.add_argument("--packages", required=True)
    many.add_argument("--source-dir", type=Path, default=Path("."))
    many.add_argument("--destination", type=Path, required=True)
    many.add_argument("--source", default="")
    many.add_argument("--job", default="")
    many.add_argument(
        "--skip-reason",
        default="No matching result files were found for this category",
    )
    many.add_argument("--fail-if-empty", action="store_true")
    many.add_argument("--github-output", type=Path, default=None)

    layout = sub.add_parser("layout", help="Fold report-* directories into results/{category}/")
    layout.add_argument("--collected-dir", type=Path, default=Path("collected"))
    layout.add_argument("--results-dir", type=Path, default=Path("results"))
    layout.add_argument("--github-output", type=Path, default=None)

    args = parser.parse_args(argv)
    if args.command == "package" and not getattr(args, "packages", ""):
        canonical_category(args.category)
    return args


if __name__ == "__main__":
    sys.exit(main())
