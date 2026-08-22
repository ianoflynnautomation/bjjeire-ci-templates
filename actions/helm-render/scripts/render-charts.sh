#!/usr/bin/env bash
#
# Render local Helm charts to plain Kubernetes YAML with `helm template`.
#
# Glob-matched chart paths render into one output directory, so a downstream
# schema or policy scan consumes a single folder instead of re-templating.
# Charts that declare dependencies are resolved first (`helm dependency build`
# when a Chart.lock exists, `update` when it does not).
#
# Inputs arrive as environment variables, set by action.yml:
#   CHART_PATHS        newline-separated chart dirs; globs expanded
#   OUTPUT_DIR         directory the rendered manifests are written to
#   RELEASE_NAME       release name; empty uses each chart's own name
#   NAMESPACE          --namespace value; empty omits the flag
#   VALUES_FILES       newline-separated --values files
#   SET_VALUES         newline-separated --set key=value pairs
#   SET_STRING_VALUES  newline-separated --set-string key=value pairs
#   INCLUDE_CRDS       "true" adds --include-crds
#   DEPENDENCY_BUILD   "true" resolves dependencies before templating
#   EXTRA_ARGS         word-split and appended to every `helm template`
#   FAIL_ON_EMPTY      "true" fails when no chart path produced output
#   SUMMARY_TITLE      step-summary heading; empty skips the summary
#
# Outputs are written to $GITHUB_OUTPUT: rendered-count, skipped-count,
# output-dir, files.

set -euo pipefail

if ! command -v helm >/dev/null 2>&1; then
  echo "::error title=Helm missing::Install Helm before this action (azure/setup-helm or ianoflynnautomation/bjjeire-ci-templates/actions/setup-kubernetes-tools)"
  exit 1
fi

mkdir -p "$OUTPUT_DIR"

# Shared flags, built once and reused for every chart.
common_args=()
[[ -n "$NAMESPACE" ]] && common_args+=(--namespace "$NAMESPACE")
[[ "$INCLUDE_CRDS" = "true" ]] && common_args+=(--include-crds)

while IFS= read -r vf; do
  vf="${vf#"${vf%%[![:space:]]*}"}"; vf="${vf%"${vf##*[![:space:]]}"}"
  [[ -n "$vf" ]] || continue
  if [[ ! -f "$vf" ]]; then
    echo "::error title=Missing values file::${vf} does not exist"
    exit 1
  fi
  common_args+=(--values "$vf")
done <<< "$VALUES_FILES"

while IFS= read -r kv; do
  kv="${kv#"${kv%%[![:space:]]*}"}"; kv="${kv%"${kv##*[![:space:]]}"}"
  [[ -n "$kv" ]] || continue
  common_args+=(--set "$kv")
done <<< "$SET_VALUES"

while IFS= read -r kv; do
  kv="${kv#"${kv%%[![:space:]]*}"}"; kv="${kv%"${kv##*[![:space:]]}"}"
  [[ -n "$kv" ]] || continue
  common_args+=(--set-string "$kv")
done <<< "$SET_STRING_VALUES"

# Named distinctly from $EXTRA_ARGS: two identifiers differing only
# in case are exactly the kind of thing an edit silently gets wrong.
read -ra caller_flags <<< "${EXTRA_ARGS:-}"

rendered=0
skipped=0
files=""
rows=""
declare -A slug_source=()
shopt -s nullglob

while IFS= read -r pattern; do
  pattern="${pattern#"${pattern%%[![:space:]]*}"}"; pattern="${pattern%"${pattern##*[![:space:]]}"}"
  [[ -n "$pattern" ]] || continue

  matched=0
  # Unquoted on purpose: applies glob expansion to the caller pattern.
  # shellcheck disable=SC2086
  for dir in $pattern; do
    matched=1
    if [[ ! -d "$dir" ]]; then
      echo "::warning title=Not a directory::${dir} is not a directory — skipping"
      skipped=$((skipped + 1))
      rows+="| \`${dir}\` | skipped (not a directory) |"$'\n'
      continue
    fi
    if [[ ! -f "${dir}/Chart.yaml" ]]; then
      echo "::notice title=No chart::${dir} has no Chart.yaml — skipping"
      skipped=$((skipped + 1))
      rows+="| \`${dir}\` | skipped (no Chart.yaml) |"$'\n'
      continue
    fi

    chart_name="$(awk '/^name:[[:space:]]/ {gsub(/^name:[[:space:]]*|["'"'"']/, ""); print; exit}' "${dir}/Chart.yaml")"
    name="${RELEASE_NAME:-$chart_name}"
    if [[ -z "$name" ]]; then
      echo "::error file=${dir}/Chart.yaml,title=Unnamed chart::Chart.yaml has no top-level 'name' and no release-name was supplied"
      exit 1
    fi

    # Only charts that declare dependencies pay for the resolve step.
    if [[ "$DEPENDENCY_BUILD" = "true" ]] && grep -q '^dependencies:' "${dir}/Chart.yaml"; then
      echo "::group::helm dependency (${dir})"
      if [[ -f "${dir}/Chart.lock" ]]; then
        helm dependency build "$dir"
      else
        echo "::notice title=No Chart.lock::${dir} has dependencies but no lock file — running 'helm dependency update'"
        helm dependency update "$dir"
      fi
      echo "::endgroup::"
    fi

    # Slugifying / to - is not injective: "charts/my-app" and
    # "charts-my/app" both become "charts-my-app". Silently overwriting
    # would drop a chart from the artifact — and from every downstream
    # policy scan — while still counting it as rendered.
    slug="${dir#./}"; slug="${slug%/}"; slug="${slug//\//-}"
    out="${OUTPUT_DIR}/${slug}.yaml"
    if [[ -n "${slug_source[$slug]:-}" ]]; then
      echo "::error title=Output collision::${dir} and ${slug_source[$slug]} both render to ${out} — rename one chart directory"
      exit 1
    fi
    if [[ -e "$out" ]]; then
      echo "::error title=Output collision::${dir} renders to ${out}, which already exists — an earlier render step into the same output-dir would be overwritten"
      exit 1
    fi
    slug_source[$slug]="$dir"

    echo "::group::helm template ${name} ${dir}"
    helm template "$name" "$dir" "${common_args[@]}" "${caller_flags[@]}" > "$out"
    echo "::endgroup::"

    rendered=$((rendered + 1))
    files+="${out} "
    docs="$(grep -c '^---' "$out" || true)"
    rows+="| \`${dir}\` | \`${chart_name}\` | \`${out}\` | ${docs} |"$'\n'
  done

  if [[ "$matched" -eq 0 ]]; then
    echo "::warning title=No match::Pattern '${pattern}' matched nothing"
    rows+="| \`${pattern}\` | — | no match | 0 |"$'\n'
  fi
done <<< "$CHART_PATHS"

{
  echo "rendered-count=${rendered}"
  echo "skipped-count=${skipped}"
  echo "output-dir=${OUTPUT_DIR}"
  echo "files=${files% }"
} >> "$GITHUB_OUTPUT"

if [[ -n "$SUMMARY_TITLE" ]]; then
  {
    echo "### ${SUMMARY_TITLE}"
    echo ""
    echo "| Chart path | Chart | Output | Documents |"
    echo "| --- | --- | --- | --- |"
    printf '%s' "$rows"
    echo ""
    echo "Rendered **${rendered}**, skipped **${skipped}**."
  } >> "$GITHUB_STEP_SUMMARY"
fi

if [[ "$rendered" -eq 0 ]]; then
  if [[ "$FAIL_ON_EMPTY" = "true" ]]; then
    echo "::error title=Nothing rendered::No path in 'chart-paths' produced output — check the patterns"
    exit 1
  fi
  echo "::warning title=Nothing rendered::No path in 'chart-paths' produced output"
fi
