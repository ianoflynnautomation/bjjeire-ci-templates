#!/usr/bin/env bash
#
# Builds a caller-supplied set of Kustomize directories (globs supported)
# into a flat output directory, one rendered YAML file per overlay.
# Directories without a kustomization file, or with an empty placeholder
# one, are skipped with an annotation instead of failing the run. Requires
# kustomize on PATH and the repo checked out.
#
# Inputs arrive as environment variables, set by action.yml:
#   PATHS
#   OUTPUT_DIR
#   LOAD_RESTRICTOR
#   KUSTOMIZE_ARGS
#   FAIL_ON_EMPTY
#   SUMMARY_TITLE
#
# Outputs are written to $GITHUB_OUTPUT.

set -euo pipefail

# Fail with one clear message rather than N confusing ones downstream.
require() {
  local tool="$1" hint="$2"
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "::error title=${tool} missing::${hint}"
    exit 1
  fi
}
require jq "jq is required to emit the rendered-files output; install it or use a runner image that ships it"

if ! command -v kustomize >/dev/null 2>&1; then
  echo "::error title=kustomize missing::kustomize is not on PATH — install it first (see actions/setup-kubernetes-tools)"
  exit 1
fi

mkdir -p "$OUTPUT_DIR"
read -ra extra_args <<< "$KUSTOMIZE_ARGS"

rendered=0
skipped=0
rows=""
files_json="[]"

# nullglob so a pattern matching nothing expands to nothing rather than
# to the literal pattern; we report those separately as unmatched.
shopt -s nullglob

echo "::group::Kustomize render"
while IFS= read -r pattern; do
  # Trim surrounding whitespace without invoking a subshell.
  pattern="${pattern#"${pattern%%[![:space:]]*}"}"
  pattern="${pattern%"${pattern##*[![:space:]]}"}"
  [[ -n "$pattern" ]] || continue

  matched=0
  # Unquoted expansion is deliberate: it applies glob expansion to the
  # caller's pattern (e.g. "kubernetes/apps/overlays/*").
  # shellcheck disable=SC2086
  for dir in $pattern; do
    matched=1
    if [[ ! -d "$dir" ]]; then
      echo "::warning title=Not a directory::${dir} is not a directory — skipping"
      skipped=$((skipped + 1))
      rows+="| \`${dir}\` | skipped (not a directory) |"$'\n'
      continue
    fi

    kfile=""
    for candidate in "${dir}/kustomization.yaml" "${dir}/kustomization.yml" "${dir}/Kustomization"; do
      if [[ -f "$candidate" ]]; then kfile="$candidate"; break; fi
    done

    if [[ -z "$kfile" ]]; then
      echo "::notice title=No kustomization::${dir} has no kustomization file — skipping"
      skipped=$((skipped + 1))
      rows+="| \`${dir}\` | skipped (no kustomization) |"$'\n'
      continue
    fi

    if [[ ! -s "$kfile" ]]; then
      echo "::warning file=${kfile},title=Empty kustomization::Skipping empty placeholder"
      skipped=$((skipped + 1))
      rows+="| \`${dir}\` | skipped (empty placeholder) |"$'\n'
      continue
    fi

    # Slugify the repo-relative path so output names are unique and
    # traceable back to the overlay that produced them.
    slug="${dir#./}"
    slug="${slug%/}"
    slug="${slug//\//-}"
    out="${OUTPUT_DIR}/${slug}.yaml"

    echo "Building ${dir} -> ${out}"
    kustomize build --load-restrictor="${LOAD_RESTRICTOR}" "${extra_args[@]}" "$dir" > "$out"

    rendered=$((rendered + 1))
    rows+="| \`${dir}\` | \`${out}\` |"$'\n'
    files_json="$(printf '%s' "$files_json" | jq -c --arg f "$out" '. + [$f]')"
  done

  if [[ "$matched" -eq 0 ]]; then
    echo "::warning title=No match::Pattern '${pattern}' matched nothing"
    rows+="| \`${pattern}\` | no match |"$'\n'
  fi
done <<< "$PATHS"
echo "::endgroup::"

{
  echo "rendered-count=${rendered}"
  echo "skipped-count=${skipped}"
  echo "rendered-files=${files_json}"
} >> "$GITHUB_OUTPUT"

if [[ -n "$SUMMARY_TITLE" ]]; then
  {
    echo "### ${SUMMARY_TITLE}"
    echo ""
    echo "| Source | Output |"
    echo "| --- | --- |"
    printf '%s' "$rows"
    echo ""
    echo "Rendered **${rendered}**, skipped **${skipped}**."
  } >> "$GITHUB_STEP_SUMMARY"
fi

if [[ "$rendered" -eq 0 ]]; then
  if [[ "$FAIL_ON_EMPTY" = "true" ]]; then
    echo "::error title=Nothing rendered::No directory in 'paths' produced output — check the patterns"
    exit 1
  fi
  echo "::warning title=Nothing rendered::No directory in 'paths' produced output"
else
  echo "::notice title=${SUMMARY_TITLE:-Kustomize render}::Rendered ${rendered} overlay(s) into ${OUTPUT_DIR}"
fi
