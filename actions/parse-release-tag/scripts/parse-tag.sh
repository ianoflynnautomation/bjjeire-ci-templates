#!/usr/bin/env bash
#
# Resolves a component release tag (api-v1.2.3, chart-web-v0.4.0) into the
# directory that owns it plus the bare version, using a prefix map the
# caller supplies. Keeps the repo-specific tag-to-path mapping in the
# caller — this action only does the matching — so tag-driven publish
# pipelines carry no hardcoded component names.
#
# Inputs arrive as environment variables, set by action.yml:
#   TAG
#   MAPPING
#   REQUIRE_MATCH
#   PATH_MUST_EXIST
#   SUMMARY_TITLE
#
# Outputs are written to $GITHUB_OUTPUT.

set -euo pipefail

tag="${TAG#"${TAG%%[![:space:]]*}"}"; tag="${tag%"${tag##*[![:space:]]}"}"
if [[ -z "$tag" ]]; then
  echo "::error title=Empty tag::'tag' is required"
  exit 1
fi

best_prefix=""
best_path=""
known=""
while IFS= read -r line; do
  line="${line#"${line%%[![:space:]]*}"}"; line="${line%"${line##*[![:space:]]}"}"
  [[ -n "$line" ]] || continue
  case "$line" in \#*) continue ;; esac
  if [[ "${line#*=}" = "$line" ]]; then
    echo "::error title=Invalid mapping::'${line}' is not a 'prefix=path' entry"
    exit 1
  fi

  prefix="${line%%=*}"
  path="${line#*=}"
  prefix="${prefix%"${prefix##*[![:space:]]}"}"
  path="${path#"${path%%[![:space:]]*}"}"
  if [[ -z "$prefix" ]] || [[ -z "$path" ]]; then
    echo "::error title=Invalid mapping::'${line}' has an empty prefix or path"
    exit 1
  fi
  known+="${prefix} "

  # Longest match wins, so mapping order does not matter.
  if [[ "${tag#"$prefix"}" != "$tag" ]] && [[ "${#prefix}" -gt "${#best_prefix}" ]]; then
    best_prefix="$prefix"
    best_path="$path"
  fi
done <<< "$MAPPING"

if [[ -z "$best_prefix" ]]; then
  {
    echo "matched=false"
    echo "prefix="
    echo "path="
    echo "version="
    echo "tag=${tag}"
  } >> "$GITHUB_OUTPUT"
  if [[ "$REQUIRE_MATCH" = "true" ]]; then
    echo "::error title=Unknown tag::'${tag}' matches no prefix in the mapping (known: ${known% })"
    exit 1
  fi
  echo "::warning title=Unknown tag::'${tag}' matches no prefix in the mapping (known: ${known% })"
  exit 0
fi

version="${tag#"$best_prefix"}"
if [[ -z "$version" ]]; then
  echo "::error title=Empty version::'${tag}' is exactly the prefix '${best_prefix}' — nothing left to use as a version"
  exit 1
fi

if [[ "$PATH_MUST_EXIST" = "true" ]] && [[ ! -d "$best_path" ]]; then
  echo "::error title=Missing path::Resolved '${best_path}' but it is not a directory in the workspace"
  exit 1
fi

{
  echo "matched=true"
  echo "prefix=${best_prefix}"
  echo "path=${best_path}"
  echo "version=${version}"
  echo "tag=${tag}"
} >> "$GITHUB_OUTPUT"
echo "::notice title=Resolved tag::${tag} -> path=${best_path} version=${version}"

if [[ -n "$SUMMARY_TITLE" ]]; then
  {
    echo "### ${SUMMARY_TITLE}"
    echo ""
    echo "| Field | Value |"
    echo "| --- | --- |"
    echo "| Tag | \`${tag}\` |"
    echo "| Prefix | \`${best_prefix}\` |"
    echo "| Path | \`${best_path}\` |"
    echo "| Version | \`${version}\` |"
  } >> "$GITHUB_STEP_SUMMARY"
fi
