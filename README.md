# bjjeire-ci-templates

Centralized reusable GitHub Actions workflows and composite actions — the golden paths for CI/CD across BjjEire repositories.

> **Setup:** after pushing, set the repo's Actions access to *"Accessible from repositories owned by the user/organization"* (Settings → Actions → General → Access) so other repos can call these workflows. Adjust the `ianoflynnautomation/` owner in the examples if the repo lives elsewhere.

## Catalog

| Workflow | Purpose |
|---|---|
| [`dotnet-build.yml`](.github/workflows/dotnet-build.yml) | Build a .NET solution once, optional `dotnet format` gate, matrix test run against shared build output |
| [`docker-build-push.yml`](.github/workflows/docker-build-push.yml) | Multi-arch buildx build with GHA cache, SBOM + provenance attestation, cosign keyless signing, Trivy scan → code scanning |
| [`terraform-plan.yml`](.github/workflows/terraform-plan.yml) | fmt + validate + plan (Azure OIDC), plan artifact + step summary, `has-changes` output |
| [`terraform-apply.yml`](.github/workflows/terraform-apply.yml) | Applies the exact plan artifact, gated by a GitHub environment (required reviewers) |

| Composite action | Purpose |
|---|---|
| [`actions/setup-dotnet-cached`](actions/setup-dotnet-cached/action.yml) | NuGet package cache (container-first jobs — no SDK install) |
| [`actions/setup-node-cached`](actions/setup-node-cached/action.yml) | node_modules cache + optional `npm ci` |
| [`actions/dotnet-run-tests`](actions/dotnet-run-tests/action.yml) | Single test project with TRX output + artifact upload |

Full input/output documentation lives in each workflow's `workflow_call` block — every input has a description, type, and default. Ready-to-copy caller workflows are in [`examples/`](examples/).

## Usage

Call a workflow:

```yaml
jobs:
  dotnet:
    permissions:
      contents: read
    uses: ianoflynnautomation/bjjeire-ci-templates/.github/workflows/dotnet-build.yml@v1
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

- **Permissions superset** — the caller job must grant every permission any job inside the reusable workflow uses, or GitHub rejects the run at parse time. Each workflow's header comment lists exactly what to grant.
- **Concurrency on the caller only** — reusable workflows inherit `github.workflow` from the caller. If both declare the same concurrency group, the run deadlocks against itself. None of the workflows here declare `concurrency`; put it on your caller.
- **Plan → apply in one run** — `terraform-apply.yml` consumes the artifact uploaded by `terraform-plan.yml`; artifacts don't cross workflow runs, so chain them with `needs:` in the same caller and gate apply with an environment.
- **Secrets** — pass explicitly (shown in examples) or use `secrets: inherit`. Explicit is preferred: it documents the contract.

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

See [CONTRIBUTING.md](CONTRIBUTING.md) before changing anything here — every consumer repo is downstream of this one.
