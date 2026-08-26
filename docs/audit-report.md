# Collect-then-merge audit report

Reusable across every consumer of **bjjeire-ci-templates**. PR and main
pipelines should **not** re-run the suite to produce the compliance PDF.
Package whatever each test job already produced, then merge.

```
any test job  ──uploads──►  raw JUnit / Cucumber / Playwright artifacts
                    │
                    ▼
         report-bundle-{source}     (package-audit-reports / audit-packages
                                    or package-test-report.yml)
                    │
                    ▼
         audit-report.yml           PDF + Step Summary + SHA-256 catalog
                                    optional attach-to-tag
```

## Adopt (any team)

1. Opt in on the golden-path workflow you already call, **or** add
   `package-test-report.yml` after a custom test job.
2. Add one `audit-report.yml` job with `needs:` those test jobs and
   `if: always()`.
3. On a GitHub Release, pass `attach-to-tag`.

| How you run tests | What to set |
| --- | --- |
| `maven-build-test.yml` | `package-audit-reports: true` and `package-audit-source: <unique>` |
| `node-build-test.yml` | `audit-packages` (`category\|glob` lines) + `artifact-name` + `upload-artifact-always: true` |
| `playwright-tests.yml` / `playwright-docker-tests.yml` | `package-audit-reports: true` |
| Anything else | `package-test-report.yml` with `download-artifact-name` + `packages` |

`packages` / `audit-packages` lines:

```
category|glob
category|source|glob[|glob...]
```

Categories: `unit`, `integration`, `acceptance` (alias `api`), `system`
(alias `ui`), `performance`. Playwright is collected from artifacts — never
run against production.

| Input | PR / main | Release pack (`audit-release.yml`) |
| --- | --- | --- |
| `strict-missing` | `false` — skipped path-filtered suites stay in the PDF as MISSING but do not fail the merge | `true` |
| `fail-on-test-failure` | `true` — a packaged suite with failing tests fails the merge | `true` |
| `attach-to-tag` | empty | release tag |

Ready-to-copy: [`examples/audit-report.yml`](../examples/audit-report.yml).
