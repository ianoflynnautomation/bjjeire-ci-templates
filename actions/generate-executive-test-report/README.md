# generate-executive-test-report

Composite action used by [`audit-report.yml`](../../.github/workflows/audit-report.yml)
(merge-only) and [`audit-release.yml`](../../.github/workflows/audit-release.yml)
(dedicated re-run pack).

Parses JUnit XML, Cucumber JSON, Playwright JSON, and optional k6/Lighthouse JSON into:

- an audit-ready PDF (`reportlab`)
- a GitHub Step Summary
- `verdict.json` (release ID, gate statuses, SHA-256 catalog)

## Collect-then-merge (any team)

Opt in on the golden-path test workflows, or call
[`package-test-report.yml`](../../.github/workflows/package-test-report.yml)
after a custom job. Then merge with
[`audit-report.yml`](../../.github/workflows/audit-report.yml).

```yaml
java:
  uses: ianoflynnautomation/bjjeire-ci-templates/.github/workflows/maven-build-test.yml@v1
  with:
    package-audit-reports: true
    package-audit-source: java

audit_report:
  needs: [java]
  if: always()
  uses: ianoflynnautomation/bjjeire-ci-templates/.github/workflows/audit-report.yml@v1
  with:
    product: My Service
    strict-missing: false
```

Custom jobs: `packages` is newline-separated `category|source|glob` (source
optional). That uploads `report-bundle-{source}`. `mode=layout` folds both
per-category `report-*` and those bundles into `results/{category}/`.

See [`docs/audit-report.md`](../../docs/audit-report.md).

Path-filtered PR/main runs should pass `strict-missing: false` so a skipped
suite is still **MISSING / CRITICAL FAILURE** in the PDF but does not fail the
merge job. Failed tests in a packaged suite still fail. Release packs keep
`strict-missing: true`.

## Modes

| `mode` | What it does |
| --- | --- |
| `package` | Copy globs (or `packages` lines) into `_meta.json` dirs; upload `report-{category}[-{source}]` or `report-bundle-{source}` |
| `layout` | Fold downloaded `report-*` and `report-bundle-*` directories into `results/{category}/` |
| `stage` | Copy bundled fixtures or write `_meta.json` (`MISSING`) for one category |
| `k6` | Run `k6/catalog-smoke.js` against `api-url`, refusing `production-hosts` |
| `generate` | Parse `results/{unit,integration,acceptance,system}/` and emit the pack |

## Preview the PDF

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python preview_report.py --clean
```

That writes `out/audit-release-report.pdf`, `out/summary.md`, and `out/verdict.json`, prints the Step Summary, and opens the PDF (`open` on macOS, `xdg-open` on Linux). Use `--no-open` in CI.

```sh
.venv/bin/python preview_report.py --no-open --out-dir /tmp/audit-preview
```

Release ID format: `REL-[YYYYMMDD]-[GIT_COMMIT_SHORT_SHA]`.

Missing required stages are **MISSING / CRITICAL FAILURE** and fail the gate; the PDF still writes.
