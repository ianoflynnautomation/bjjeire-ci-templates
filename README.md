# bjjeire-ci-templates

Centralized reusable GitHub Actions workflows and composite actions — the golden paths for CI/CD across BjjEire repositories.

> **Setup:** after pushing, set the repo's Actions access to *"Accessible from repositories owned by the user/organization"* (Settings → Actions → General → Access) so other repos can call these workflows. Adjust the `ianoflynnautomation/` owner in the examples if the repo lives elsewhere.

## Catalog

| Workflow | Purpose |
|---|---|
| [`dotnet-build-test.yml`](.github/workflows/dotnet-build-test.yml) | Build a .NET solution once, optional `dotnet format` gate, matrix test run against shared build output |
| [`maven-build-test.yml`](.github/workflows/maven-build-test.yml) | `mvn verify` (surefire + failsafe) on the host runner for Testcontainers, optional JUnit report check |
| [`node-build-test.yml`](.github/workflows/node-build-test.yml) | Container-first Node job: node_modules cache, install, ordered commands, artifact in/out + failure diagnostics |
| [`playwright-tests.yml`](.github/workflows/playwright-tests.yml) | Sharded Playwright run against an environment that already exists — plans the matrix, runs shards, merges and gates |
| [`playwright-docker-tests.yml`](.github/workflows/playwright-docker-tests.yml) | Sharded Playwright run that provisions its own Docker Compose stack per shard, plus a sticky PR result comment |
| [`playwright-report.yml`](.github/workflows/playwright-report.yml) | Shared tail for any sharded Playwright run: merge blob reports, summarise counts, publish to Pages, gate on failures/flakes |
| [`acceptance-gate.yml`](.github/workflows/acceptance-gate.yml) | Deploy → test → teardown orchestrator. `mode: ephemeral` applies gitops sha-env + waits for the Flux HelmRelease; `mode: existing` runs the same suite against URLs you pass in |
| [`flux-ephemeral-teardown.yml`](.github/workflows/flux-ephemeral-teardown.yml) | Label-guarded destroy of an ephemeral namespace (Helm uninstall + optional Flux HelmRelease delete + namespace delete) |
| [`docker-build-push.yml`](.github/workflows/docker-build-push.yml) | Multi-arch buildx build with GHA cache, SBOM + provenance attestation, cosign keyless signing, Trivy scan → code scanning |
| [`security-scan.yml`](.github/workflows/security-scan.yml) | Dependency review + gitleaks secret scan + Semgrep SAST, each independently toggleable |
| [`terraform-quality.yml`](.github/workflows/terraform-quality.yml) | Credential-free tier: fmt + backend-less validate + tflint (root and per-module) + opt-in terraform-docs drift check, sticky PR comment, per-check gate. Runs on fork PRs |
| [`iac-scan.yml`](.github/workflows/iac-scan.yml) | Trivy misconfiguration scan over IaC source (Terraform, CFN, Helm, Dockerfile) → SARIF to code scanning |
| [`terraform-plan.yml`](.github/workflows/terraform-plan.yml) | fmt + validate + plan (Azure OIDC), plan artifact + step summary, `has-changes` output |
| [`terraform-apply.yml`](.github/workflows/terraform-apply.yml) | Applies the exact plan artifact, gated by a GitHub environment (required reviewers) |
| [`terraform-drift-detection.yml`](.github/workflows/terraform-drift-detection.yml) | Scheduled plan against live state; opens one label-tracked issue on drift and closes it when clean |
| [`terraform-destroy.yml`](.github/workflows/terraform-destroy.yml) | Guarded teardown: deny-list, typed confirmation, environment gate, dry-run; applies a saved destroy plan |
| [`kubernetes-manifest-validation.yml`](.github/workflows/kubernetes-manifest-validation.yml) | Render Kustomize overlays (globs, no cluster list), helm lint, kubeconform schema gate, content deny-pattern, rendered-manifests artifact |
| [`kubernetes-policy-scan.yml`](.github/workflows/kubernetes-policy-scan.yml) | Trivy misconfig (+ SARIF to code scanning), Polaris audit, opt-in kube-score and hadolint over already-rendered manifests |
| [`helm-chart-quality.yml`](.github/workflows/helm-chart-quality.yml) | Helm sibling of the Kustomize workflow: discover charts by glob, lint, `helm template` the release charts, kubeconform gate, rendered-manifests artifact |
| [`helm-publish-oci.yml`](.github/workflows/helm-publish-oci.yml) | Package + push a chart to any OCI registry, name/version read from Chart.yaml, tag-version assertion and pull-back verification |
| [`flux-local.yml`](.github/workflows/flux-local.yml) | Offline Flux verification: `flux-local test` per cluster, plus a PR-vs-base `diff` posted as a sticky comment |
| [`release-please.yml`](.github/workflows/release-please.yml) | release-please in single-package or manifest mode, normalised outputs (`paths-released`/`tags-released`), floating-major-tag move |
| [`release-dispatch.yml`](.github/workflows/release-dispatch.yml) | Fires a `workflow_dispatch` per released package from `tags-released`. Separate from `release-please.yml` so only monorepo callers pay `actions: write` |
| [`renovate.yml`](.github/workflows/renovate.yml) | Self-hosted Renovate run with runtime-substituted host rules for private registries |
| [`lint-workflows.yml`](.github/workflows/lint-workflows.yml) | actionlint + zizmor + deprecated-command gate for a repo's workflow files, optional yamllint (file or inline config) |
| [`sync-labels.yml`](.github/workflows/sync-labels.yml) | Upsert repository labels from a version-controlled YAML file (never deletes; `dry-run` supported) |
| [`cleanup-artifacts.yml`](.github/workflows/cleanup-artifacts.yml) | Scheduled cleanup of artifacts and stale non-default-branch workflow runs (caches opt-in) |
| [`executive-test-report.yml`](.github/workflows/executive-test-report.yml) | Combined PDF of unit/integration/API/UI/performance collectors |
| [`package-test-report.yml`](.github/workflows/package-test-report.yml) | Generic collect step: download any team's test artifact and emit `report-bundle-*` for the audit PDF |
| [`audit-report.yml`](.github/workflows/audit-report.yml) | Merge-only audit PDF: download `report-*` artifacts, SHA-256 catalog, optional GitHub Release attach |
| [`audit-release.yml`](.github/workflows/audit-release.yml) | Dedicated compliance pack that re-runs unit/integration and stages acceptance/system; prefer `audit-report.yml` on PR/main |

| Composite action | Purpose |
|---|---|
| [`actions/setup-dotnet-cached`](actions/setup-dotnet-cached/action.yml) | NuGet package cache (container-first jobs — no SDK install) |
| [`actions/setup-node-cached`](actions/setup-node-cached/action.yml) | node_modules cache + optional `npm ci` |
| [`actions/setup-java-cached`](actions/setup-java-cached/action.yml) | JDK install + Maven/Gradle dependency cache; `install-jdk: false` restores only the cache in container-first jobs |
| [`actions/azure-aks-login`](actions/azure-aks-login/action.yml) | Azure OIDC login → kubelogin/kubectl/helm → AKS kubeconfig, with a reachability check |
| [`actions/wait-for-http`](actions/wait-for-http/action.yml) | Poll a URL until it answers an accepted status class; falls back to python3 on images without curl |
| [`actions/flux-wait-helmrelease`](actions/flux-wait-helmrelease/action.yml) | Wait until a Flux HelmRelease is Ready, then emit public and in-cluster URLs |
| [`actions/collect-k8s-diagnostics`](actions/collect-k8s-diagnostics/action.yml) | Dump events, pod status, logs, and optional helm/flux status; intended for `if: failure()` |
| [`actions/playwright-plan-matrix`](actions/playwright-plan-matrix/action.yml) | Expand Playwright projects × shards into a flat matrix, with per-project shard and config overrides |
| [`actions/export-test-env`](actions/export-test-env/action.yml) | Compose a test environment from KEY=VALUE payloads with `::add-mask::` on every secret; writes to `$GITHUB_ENV` or a mode-600 file for `docker --env-file`, plus per-project overrides |
| [`actions/dotnet-run-tests`](actions/dotnet-run-tests/action.yml) | Single test project with TRX output + artifact upload |
| [`actions/detect-changes`](actions/detect-changes/action.yml) | Evaluate caller-supplied path filters; emits a `changes` JSON array + summary. Filters stay in the caller |
| [`actions/check-required-jobs`](actions/check-required-jobs/action.yml) | Aggregate branch-protection gate over `toJson(needs)` — fails on failure/cancelled, passes on path-filter skips |
| [`actions/sticky-comment`](actions/sticky-comment/action.yml) | Marker-identified issue/PR comment that updates in place instead of spamming the thread |
| [`actions/maven-openapi-export`](actions/maven-openapi-export/action.yml) | Run the failsafe IT that writes the OpenAPI document, then validate the JSON |
| [`actions/openapi-breaking-gate`](actions/openapi-breaking-gate/action.yml) | Pull the last published OpenAPI contract from an OCI registry and fail on breaking changes (oasdiff); skips only on genuine first publish |
| [`actions/oci-push-artifact`](actions/oci-push-artifact/action.yml) | Publish a file to any OCI registry as a typed artifact with ORAS; extra tags alias one digest |
| [`actions/oci-tag-audit`](actions/oci-tag-audit/action.yml) | Assert caller-supplied `repository:tag` refs exist in any Registry v2 host; fails closed on probe errors. Extracting the pins stays in the caller |
| [`actions/setup-kubernetes-tools`](actions/setup-kubernetes-tools/action.yml) | Flux CLI, Kustomize, kubeconform and Helm — each installed only when you pass its version |
| [`actions/kustomize-render`](actions/kustomize-render/action.yml) | Build a glob-matched set of overlays into one output dir; empty/missing kustomizations annotate instead of failing |
| [`actions/helm-render`](actions/helm-render/action.yml) | `helm template` a glob-matched set of charts into one output dir, resolving dependencies first; non-charts annotate instead of failing |
| [`actions/helm-push-oci`](actions/helm-push-oci/action.yml) | Package and push a chart to any OCI registry, name/version from Chart.yaml, with an expected-version assertion and pull-back verification |
| [`actions/parse-release-tag`](actions/parse-release-tag/action.yml) | Resolve a component tag (`api-v1.2.3`) to its directory and bare version via a caller-supplied prefix map. The map stays in the caller |
| [`actions/generate-executive-test-report`](actions/generate-executive-test-report/action.yml) | `package` live results after a test job, `layout` downloaded `report-*` artifacts, run k6, or emit the audit PDF |

Full input/output documentation lives in each workflow's `workflow_call` block — every input has a description, type, and default. Ready-to-copy caller workflows are in [`examples/`](examples/).

> **Moving a Flux GitOps repo onto these?** Cluster lists become globs, rendering happens once and is shared by artifact, and check names change. See [`docs/migrating-gitops-workflows.md`](docs/migrating-gitops-workflows.md).

> **Moving a Helm chart repo onto these?** The chart list becomes a glob, rendering happens once and is shared by artifact, and the tag-to-chart map is the only repo-specific line left in the publish caller. See [`docs/migrating-helm-chart-workflows.md`](docs/migrating-helm-chart-workflows.md).

> **Migrating from the Playwright workflows in `bjjeire-tests`?** The inputs were renamed to `kebab-case`, the fourteen named secrets collapsed into one `test-env-vars` payload, and `runner_label` became `runs-on` with a different default. See [`docs/migrating-playwright-workflows.md`](docs/migrating-playwright-workflows.md).

> **Audit PDF on PR/main?** Package each test job's artifacts with `generate-executive-test-report` `mode=package`, then call `audit-report.yml`. Do not re-run the suite. See [`docs/audit-report.md`](docs/audit-report.md).

## Usage

Call a workflow:

```yaml
jobs:
  dotnet:
    permissions:
      contents: read
      checks: write   # when publish-test-report: true
    uses: ianoflynnautomation/bjjeire-ci-templates/.github/workflows/dotnet-build-test.yml@v1
    with:
      solution-path: MyApp.sln
```

Use a composite action:

```yaml
steps:
  - uses: actions/checkout@<sha>  # v7
  - uses: ianoflynnautomation/bjjeire-ci-templates/actions/setup-node-cached@v1
    with:
      working-directory: src/my-app
      install: 'true'
```

### Rules for callers

- **Pin `@v1` (or `@vX.Y.Z`), never `@main`** — floating major tags move on release; `@main` is an unstable moving target and breaks the SemVer contract.
- **Permissions superset** — the caller job must grant every permission any job inside the reusable workflow uses, or GitHub rejects the run at parse time. Each workflow's header comment lists exactly what to grant. Conditional jobs still need the superset at the caller.
- **Concurrency on the caller only** — reusable workflows inherit `github.workflow` from the caller. If both declare the same concurrency group, the run deadlocks against itself. None of the workflows here declare `concurrency`; put it on your caller.
- **Plan → apply in one run** — `terraform-apply.yml` consumes the artifact uploaded by `terraform-plan.yml`; artifacts don't cross workflow runs, so chain them with `needs:` in the same caller and gate apply with an environment. The plan artifact is a binary plan file and Terraform stores values in it in cleartext, including `sensitive` ones — it is kept at `retention-days: 1` for that reason. `terraform-drift-detection.yml` deliberately uploads nothing, since nothing consumes its plan.
- **Secrets** — pass explicitly (shown in examples) or use `secrets: inherit`. Explicit is preferred: it documents the contract.
- **Relative composite paths don't work cross-repo** — `uses: ./actions/...` inside a reusable workflow resolves against the *caller*. Composites are consumed via `owner/repo/actions/name@v1`; language cache steps inside reusable workflows are inlined for that reason.

## Versioning

- Releases are cut by release-please from conventional commits — SemVer tags `vX.Y.Z`.
- The floating major tag (`v1`) is force-moved to each new release. **Consumers pin `@v1`** to get non-breaking updates automatically, or pin an exact `@vX.Y.Z` for full reproducibility.
- Breaking changes (renamed/removed inputs, changed defaults, new required permissions) bump the major. The previous major keeps receiving critical fixes for 90 days after a new major ships.
- Never reference `@main` from a consumer repo.

## Design conventions

- **Container-first** — language jobs run in `container:` images (`mcr.microsoft.com/dotnet/sdk`, `node:*-slim`); the image is the single source of truth for the toolchain version. Setup actions only cache.
- **SHA-pinned actions** — every third-party action is pinned to a full commit SHA with a `# vX.Y.Z` comment; Dependabot bumps weekly.
- **Secrets via `env:` only** — never interpolate `${{ secrets.X }}` into a script body.
- **Observability** — `::group::`/`::notice`/`::error title=` conventions and a `$GITHUB_STEP_SUMMARY` table in every workflow.
- **OIDC over static credentials** — Terraform auth uses Azure workload identity (`ARM_USE_OIDC`); image signing and provenance use keyless OIDC.
- **Project-agnostic inputs** — no org/repo paths, image names, or cloud resource IDs baked into defaults. Callers supply those.
- **`runs-on` is an input** — default `ubuntu-latest`; override for larger or self-hosted runners without forking the workflow.

## Security notes

| Area | Approach |
|---|---|
| Permissions | Least privilege per job; caller must still declare the superset |
| Credentials | Azure OIDC for Terraform; GHCR via `GITHUB_TOKEN`; optional registry secrets |
| Image supply chain | Provenance + SBOM attestation, cosign keyless signing, Trivy SARIF → code scanning |
| Build args | `SECRET_BUILD_ARGS` is for public SPA config only — never bake real credentials into images |
| OpenAPI gate | Fail closed on probe errors; `treat-registry-denied-as-missing` documents the GHCR first-publish tradeoff |
| Cleanup | Cache deletion is **opt-in** (`delete-caches: false` by default) |

## Governance

See [CONTRIBUTING.md](CONTRIBUTING.md) for the change process, deprecation policy, and ownership model. `.github/CODEOWNERS` requires maintainer review on every path.
