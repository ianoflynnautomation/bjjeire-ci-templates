#!/usr/bin/env bash
#
# Expands a list of Playwright projects and a shard budget into a flat
# GitHub Actions matrix, one entry per project/shard pair. Supports
# per-project shard overrides (spend shards where the suite is slow) and a
# per-project config-file map, so a single matrix can span separate API and
# UI Playwright configs.
#
# Inputs arrive as environment variables, set by action.yml:
#   PROJECTS
#   SHARD_TOTAL
#   OVERRIDES
#   CONFIG_MAP
#   DEFAULT_CONFIG
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
require jq "jq is required to plan the matrix; it ships on GitHub-hosted runners but not in every container image"

if ! [[ "$SHARD_TOTAL" =~ ^[0-9]+$ ]] || [[ "$SHARD_TOTAL" -lt 1 ]]; then
  echo "::error title=Invalid shard-total::'${SHARD_TOTAL}' must be a positive integer"
  exit 1
fi

# Accept commas as well as newlines so a caller can pass a short list
# inline without a block scalar.
projects_json=$(printf '%s\n' "${PROJECTS//,/$'\n'}" | jq -R -n -c \
  '[inputs | gsub("^\\s+|\\s+$"; "") | select(length > 0)]')

if [[ "$(jq 'length' <<< "$projects_json")" -eq 0 ]]; then
  echo "::error title=No projects::The projects input resolved to an empty list"
  exit 1
fi

overrides_json=$(printf '%s\n' "$OVERRIDES" | jq -R -n -c \
  '[inputs | gsub("\\s"; "") | select(length > 0)
    | capture("^(?<k>[^=]+)=(?<v>[0-9]+)$")
    | {(.k): (.v | tonumber)}] | add // {}')

config_json=$(printf '%s\n' "$CONFIG_MAP" | jq -R -n -c \
  '[inputs | gsub("^\\s+|\\s+$"; "") | select(length > 0)
    | capture("^(?<k>[^=]+)=(?<v>.+)$")
    | {(.k | gsub("\\s"; "")): (.v | gsub("^\\s+|\\s+$"; ""))}] | add // {}')

# An override naming a project that is not being run is nearly always a
# typo, and silently ignoring it wastes a whole CI cycle to discover.
for key in $(jq -r 'keys[]' <<< "$overrides_json") $(jq -r 'keys[]' <<< "$config_json"); do
  if [[ "$(jq --arg k "$key" 'index($k) != null' <<< "$projects_json")" != "true" ]]; then
    echo "::warning title=Unused override::'${key}' is named in project-shard-overrides or config-map but is not in the projects list"
  fi
done

plan=$(jq -nc \
  --argjson projects "$projects_json" \
  --argjson overrides "$overrides_json" \
  --argjson configs "$config_json" \
  --argjson defaultShards "$SHARD_TOTAL" \
  --arg defaultConfig "$DEFAULT_CONFIG" '
  [ $projects[]
    | . as $p
    | {
        name: $p,
        config: (($configs[$p]) // $defaultConfig),
        shard_total: (($overrides[$p]) // $defaultShards)
      }
  ]')

matrix=$(jq -c '[ .[] | . as $e | [range(1; $e.shard_total + 1)]
                  | .[] | { name: $e.name, config: $e.config, shard: ., shard_total: $e.shard_total } ]' <<< "$plan")

job_count=$(jq 'length' <<< "$matrix")
project_count=$(jq 'length' <<< "$plan")

{
  echo "matrix=${matrix}"
  echo "projects=${plan}"
  echo "job-count=${job_count}"
  echo "project-count=${project_count}"
} >> "$GITHUB_OUTPUT"

echo "::group::Planned matrix"
jq -r '.[] | "  \(.name)  shards=\(.shard_total)  config=\(.config)"' <<< "$plan"
echo "::endgroup::"
echo "::notice title=Matrix planned::${project_count} project(s) → ${job_count} shard job(s)"
