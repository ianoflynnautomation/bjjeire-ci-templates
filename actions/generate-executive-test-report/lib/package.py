"""Copy live test outputs into per-category report artifacts, then layout them."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from glob import glob
from pathlib import Path
from typing import Iterable

from .models import CATEGORY_ORDER, CategoryId, canonical_category

_META_NAME = "_meta.json"
_REPORT_PREFIX = "report-"
_BUNDLE_PREFIX = "report-bundle-"


@dataclass(frozen=True)
class PackageSpec:
    category: CategoryId
    source: str
    globs: tuple[str, ...]


def parse_package_spec(raw: str, default_source: str = "") -> list[PackageSpec]:
    """Parse newline-separated `category|source|glob[|glob...]` (source optional).

    Two fields (`category|glob`) use default_source. A field is a glob when it
    contains `*`, `/`, or `.`; otherwise the second field is the source label.
    """
    specs: list[PackageSpec] = []
    for line in raw.replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = [part.strip() for part in stripped.split("|") if part.strip()]
        if len(parts) < 2:
            raise ValueError(
                f"Invalid audit package line {line!r}; expected "
                "category|glob or category|source|glob[|glob...]"
            )
        category = canonical_category(parts[0])
        if _looks_like_glob(parts[1]):
            source = default_source
            globs = parts[1:]
        else:
            source = parts[1]
            globs = parts[2:]
        if not globs:
            raise ValueError(f"Invalid audit package line {line!r}; missing glob")
        specs.append(PackageSpec(category=category, source=source, globs=tuple(globs)))
    if not specs:
        raise ValueError("No audit package lines to process")
    return specs


def _looks_like_glob(value: str) -> bool:
    return any(token in value for token in ("*", "/", "."))


def parse_globs(raw: str | Iterable[str]) -> list[str]:
    if isinstance(raw, str):
        lines = raw.replace("\r\n", "\n").split("\n")
    else:
        lines = list(raw)
    return [line.strip() for line in lines if line.strip()]


def match_globs(source_dir: Path, patterns: Iterable[str]) -> list[Path]:
    root = source_dir.resolve()
    found: list[Path] = []
    seen: set[Path] = set()
    for pattern in patterns:
        matches = glob(str(root / pattern), recursive=True)
        for match in matches:
            path = Path(match)
            if not path.is_file():
                continue
            if path.name == _META_NAME:
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            found.append(resolved)
    found.sort()
    return found


def copy_into_category(
    files: Iterable[Path],
    destination: Path,
    *,
    source_dir: Path,
    source: str = "",
) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    _ = source
    root = source_dir.resolve()
    for path in files:
        try:
            relative = path.resolve().relative_to(root)
        except ValueError:
            relative = Path(path.name)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied.append(target)
    return copied


def write_meta(
    destination: Path,
    *,
    category: CategoryId,
    source: str,
    job: str,
    status: str,
    reason: str,
    files: Iterable[Path],
    globs: Iterable[str],
) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "reason": reason,
        "category": category,
        "source": source,
        "job": job or source or category,
        "files": [path.name for path in files],
        "globs": list(globs),
    }
    path = destination / _META_NAME
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def artifact_name(category: CategoryId, source: str = "") -> str:
    suffix = _safe_segment(source)
    if suffix:
        return f"report-{category}-{suffix}"
    return f"report-{category}"


def bundle_artifact_name(source: str = "", job: str = "") -> str:
    suffix = _safe_segment(source) or _safe_segment(job) or "pack"
    return f"{_BUNDLE_PREFIX}{suffix}"


def parse_artifact_dirname(name: str) -> tuple[CategoryId | None, str]:
    raw = name.strip().rstrip("/")
    if raw.startswith(_REPORT_PREFIX):
        raw = raw[len(_REPORT_PREFIX) :]
    if not raw:
        return None, ""
    parts = raw.split("-")
    for length in range(len(parts), 0, -1):
        candidate = "-".join(parts[:length])
        try:
            category = canonical_category(candidate)
        except ValueError:
            continue
        source = "-".join(parts[length:])
        return category, source
    return None, raw


def layout_collected(collected_dir: Path, results_dir: Path) -> list[Path]:
    """Fold downloaded report-* (and report-bundle-*) dirs into results/{category}/."""
    results_dir.mkdir(parents=True, exist_ok=True)
    laid_out: list[Path] = []
    if not collected_dir.is_dir():
        return laid_out
    for child in sorted(p for p in collected_dir.iterdir() if p.is_dir()):
        laid_out.extend(_layout_node(child, results_dir))
    return laid_out


def _layout_node(node: Path, results_dir: Path) -> list[Path]:
    category, source = _category_from_dir(node)
    if category is not None:
        return [_copy_category(node, results_dir, category, source)]
    laid: list[Path] = []
    for grandchild in sorted(p for p in node.iterdir() if p.is_dir()):
        nested_category, nested_source = _category_from_dir(grandchild)
        if nested_category is None:
            continue
        laid.append(_copy_category(grandchild, results_dir, nested_category, nested_source))
    return laid


def _copy_category(src: Path, results_dir: Path, category: CategoryId, source: str) -> Path:
    segment = _safe_segment(source)
    dest = results_dir / category / segment if segment else results_dir / category
    dest.parent.mkdir(parents=True, exist_ok=True)
    if segment and dest.exists():
        dest = results_dir / category / src.name
    _copy_tree(src, dest)
    return dest


def package_category(
    *,
    category: str,
    source_dir: Path,
    destination: Path,
    globs: str | Iterable[str],
    source: str = "",
    job: str = "",
    skip_reason: str = "No matching result files were found",
) -> dict[str, object]:
    canonical = canonical_category(category)
    patterns = parse_globs(globs)
    files = match_globs(source_dir, patterns)
    copied = copy_into_category(files, destination, source_dir=source_dir, source=source)
    status = "success" if copied else "skipped"
    reason = (
        f"Packaged {len(copied)} file(s) for {canonical}"
        if copied
        else skip_reason
    )
    write_meta(
        destination,
        category=canonical,
        source=source,
        job=job,
        status=status,
        reason=reason,
        files=copied,
        globs=patterns,
    )
    return {
        "category": canonical,
        "source": source,
        "status": status,
        "reason": reason,
        "files": len(copied),
        "destination": str(destination),
        "artifact_name": artifact_name(canonical, source),
    }


def package_many(
    *,
    packages: str,
    source_dir: Path,
    destination: Path,
    source: str = "",
    job: str = "",
    skip_reason: str = "No matching result files were found for this category",
) -> dict[str, object]:
    specs = parse_package_spec(packages, default_source=source)
    results = []
    for spec in specs:
        row_source = spec.source or source
        row_dest = destination / spec.category
        results.append(
            package_category(
                category=spec.category,
                source_dir=source_dir,
                destination=row_dest,
                globs=spec.globs,
                source=row_source,
                job=job,
                skip_reason=skip_reason,
            )
        )
    return {
        "status": "success" if any(row["status"] == "success" for row in results) else "skipped",
        "files": sum(int(row["files"]) for row in results),
        "destination": str(destination),
        "artifact_name": bundle_artifact_name(source, job),
        "categories": results,
    }


def _category_from_dir(directory: Path) -> tuple[CategoryId | None, str]:
    meta_path = directory / _META_NAME
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            meta = {}
        raw_category = str(meta.get("category") or "")
        raw_source = str(meta.get("source") or "")
        if raw_category:
            try:
                return canonical_category(raw_category), raw_source
            except ValueError:
                pass
    parsed = parse_artifact_dirname(directory.name)
    if parsed[0] is not None:
        return parsed
    if directory.name in CATEGORY_ORDER:
        return directory.name, ""  # type: ignore[return-value]
    return None, ""


def _copy_tree(src: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for path in src.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(src)
        target = dest / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def _safe_segment(value: str) -> str:
    cleaned = re.sub(r"[\s/]+", "-", (value or "").strip().lower())
    cleaned = re.sub(r"[^a-z0-9._-]", "", cleaned)
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-._")
    return cleaned
