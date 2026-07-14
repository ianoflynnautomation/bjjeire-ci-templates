# Contributing

Changes here fan out to every consumer repo. Treat every edit as a public API change.

## Ground rules

1. **Conventional commits** — release-please derives versions from them. `feat:` = minor, `fix:` = patch, `feat!:`/`BREAKING CHANGE:` = major.
2. **What counts as breaking**: renaming/removing an input, output, or secret; changing a default; requiring a new caller permission; changing artifact names or shapes. Adding an optional input with a backward-compatible default is a minor.
3. **Every input needs** a `description`, a `type`, and (unless required) a sensible `default`. Outputs need descriptions. Update the workflow's header comment when required caller permissions change.
4. **Pin actions to full commit SHAs** with a `# vX.Y.Z` trailing comment. Never `@main` or a bare tag. Dependabot bumps SHAs weekly.
5. **No top-level `concurrency` in reusable workflows** — it inherits `github.workflow` from the caller and deadlocks against a caller that declares the same group.
6. **Secrets via `env:` only** — never interpolate `${{ secrets.X }}` (or any untrusted context like `github.event.*`) directly into a `run:` script body.
7. **`timeout-minutes` on every job.** Least-privilege `permissions` per job, declared at job level.
8. **Container-first** — prefer `container:` images over host-runner `setup-*` actions for language toolchains.
9. **Logging** — wrap multi-line phases in `::group::`/`::endgroup::`, use `::notice`/`::warning`/`::error` with `title=`, and write a step summary for anything a human checks after the run.
10. **Keep workflows generic** — no repo-specific paths, image names, or secrets baked in. Repo-specific glue belongs in the caller; if you need it twice, make it an input.

## Workflow for changes

1. Branch, edit, and open a PR — CI runs actionlint + zizmor over everything.
2. Test against a real consumer before merging: point a branch of a consumer repo at your branch ref (`uses: ...@your-branch`) and run it. Revert the consumer to `@v1` after.
3. Update `examples/` and the README catalog if the contract changed.
4. Merge; release-please opens/updates the release PR. Merging that PR tags the release and moves the floating major tag.

## Adding a new workflow

- Put it in `.github/workflows/<name>.yml` with a header comment stating purpose and required caller permissions.
- Add a ready-to-copy caller under `examples/`.
- Add a row to the README catalog.
- Extract a composite action only when logic is shared by 2+ workflows or repos — thin single-caller wrappers just split the file.

## Deprecation policy

- Deprecate before removing: keep the old input/workflow working for one minor release, emitting a `::warning title=Deprecated::` pointing at the replacement.
- Previous major versions receive critical fixes for 90 days after a new major ships.
