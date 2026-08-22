#!/usr/bin/env bash
#
# Compose a test environment from newline-separated KEY=VALUE payloads.
#
# Three payloads are written in precedence order — base, plain, secret — and
# then per-project overrides land last so they win. Every value in the secret
# payload is registered with ::add-mask:: before it is written anywhere.
#
# Multi-line values are impossible by construction: the payload format splits
# on newlines, so a value containing one becomes a second line that fails the
# KEY=VALUE check and aborts the run. That is deliberate — it is also what
# keeps a secret from injecting extra entries into $GITHUB_ENV.
#
# Inputs arrive as environment variables (never as arguments) so that secret
# values never appear in a process listing:
#   TARGET             github-env | file
#   FILE_PREFIX        basename prefix when TARGET=file
#   BASE_VARS          unmasked, written first, no notice emitted
#   PLAIN_ENV_VARS     unmasked
#   SECRET_ENV_VARS    masked
#   PROJECT_OVERRIDES  <project>:KEY=VALUE, applied last
#   PROJECT_NAME       selects which override lines apply

set -euo pipefail

target="${TARGET:-github-env}"
plain_count=0
masked_count=0
override_count=0

case "$target" in
  github-env)
    if [[ -z "${GITHUB_ENV:-}" ]]; then
      echo "::error title=Environment::GITHUB_ENV is unset — target 'github-env' only works inside a step"
      exit 1
    fi
    env_file="$GITHUB_ENV"
    # Deliberately not reported as `path`: $GITHUB_ENV is the runner's own
    # command file, not something a caller may hand to `docker --env-file`.
    reported_path=""
    ;;
  file)
    if [[ -z "${RUNNER_TEMP:-}" ]]; then
      echo "::error title=Environment::RUNNER_TEMP is unset — target 'file' needs a runner temp directory"
      exit 1
    fi
    # Written to RUNNER_TEMP (never the workspace) so it cannot be swept into
    # an uploaded artifact, and mode 600 so other processes on the runner
    # cannot read the credentials. mktemp under umask 077 gives both, and
    # unlike a $RANDOM name it cannot collide between concurrent shards. The
    # X's must trail the template with no suffix after them — GNU mktemp
    # tolerates a suffix, BSD mktemp silently returns the literal X's.
    prefix="${FILE_PREFIX:-test-env}"
    prefix="${prefix//[^A-Za-z0-9._-]/-}"
    umask 077
    env_file="$(mktemp "${RUNNER_TEMP}/${prefix}-XXXXXXXX")"
    reported_path="$env_file"
    ;;
  *)
    echo "::error title=Environment::Unknown target '${target}' — expected 'github-env' or 'file'"
    exit 1
    ;;
esac

# Appends one KEY=VALUE payload. $1 masks every value, $2 is the payload, $3
# labels the summary notice — pass an empty label to write silently. Sets
# $written to the number of lines appended.
written=0
write_vars() {
  local mask="$1" payload="$2" label="$3" line key
  written=0

  if [[ -z "${payload//[[:space:]]/}" ]]; then
    return 0
  fi

  while IFS= read -r line; do
    if [[ -z "${line//[[:space:]]/}" ]]; then
      continue
    fi

    case "$line" in
      *=*) ;;
      *)
        echo "::error title=Environment::Not a KEY=VALUE pair: ${line%%=*}"
        exit 1
        ;;
    esac

    key="${line%%=*}"
    if ! [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
      echo "::warning title=Environment::'${key}' is not a valid shell identifier — the runner may not export it"
    fi

    # An empty value would emit a bare ::add-mask:: that masks nothing and
    # warns on newer runners.
    if [[ "$mask" = "true" ]] && [[ -n "${line#*=}" ]]; then
      echo "::add-mask::${line#*=}"
    fi

    printf '%s\n' "$line" >> "$env_file"
    written=$((written + 1))
  done <<< "$payload"

  if [[ -n "$label" ]]; then
    echo "::notice title=Environment::Exported ${written} ${label} variable(s)"
  fi
}

write_vars false "${BASE_VARS:-}" ""
write_vars false "${PLAIN_ENV_VARS:-}" "plain"
plain_count="$written"
write_vars true "${SECRET_ENV_VARS:-}" "masked"
masked_count="$written"

# Per-project overrides land last so they win. Each line is
# `<project>:KEY=VALUE`; split on the first colon only, so values containing
# colons (URLs) survive intact.
overrides="${PROJECT_OVERRIDES:-}"
if [[ -n "${overrides//[[:space:]]/}" ]]; then
  if [[ -z "${PROJECT_NAME:-}" ]]; then
    echo "::error title=Environment::project-env-overrides was supplied without project-name"
    exit 1
  fi

  while IFS= read -r line; do
    if [[ -z "${line//[[:space:]]/}" ]]; then
      continue
    fi

    case "$line" in
      *:*=*) ;;
      *)
        echo "::error title=Environment::Not a <project>:KEY=VALUE entry: ${line}"
        exit 1
        ;;
    esac

    entry_project="${line%%:*}"
    assignment="${line#*:}"
    if [[ "${entry_project//[[:space:]]/}" != "$PROJECT_NAME" ]]; then
      continue
    fi

    printf '%s\n' "$assignment" >> "$env_file"
    override_count=$((override_count + 1))
  done <<< "$overrides"

  if [[ "$override_count" -gt 0 ]]; then
    echo "::notice title=Environment::Applied ${override_count} override(s) for project '${PROJECT_NAME}'"
  fi
fi

{
  echo "path=${reported_path}"
  echo "plain-count=${plain_count}"
  echo "masked-count=${masked_count}"
  echo "override-count=${override_count}"
} >> "$GITHUB_OUTPUT"
