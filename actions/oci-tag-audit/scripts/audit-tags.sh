#!/usr/bin/env bash
#
# Asserts that a caller-supplied list of registry artifacts (repository +
# tag) actually exists in an OCI registry, so a manifest pinned to a tag
# that was never published fails CI instead of failing a deployment. Works
# against any Docker Registry v2 API (GHCR, Docker Hub, ACR, ECR, Quay) via
# the standard token challenge. Extracting the pins from your manifests is
# caller glue — this action only verifies them.
#
# Inputs arrive as environment variables, set by action.yml:
#   ARTIFACTS
#   REGISTRY
#   REGISTRY_USERNAME
#   REGISTRY_PASSWORD
#   FAIL_ON_MISSING
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
require curl "curl is required to probe the registry API"
require jq "jq is required to parse the artifacts input and registry responses"

if ! printf '%s' "$ARTIFACTS" | jq -e 'type == "array"' >/dev/null 2>&1; then
  echo "::error title=Invalid input::'artifacts' must be a JSON array of objects"
  exit 1
fi

# Credentials never reach argv: the basic header is derived through a
# pipe, and only the derived value is passed to curl.
auth_basic=""
if [[ -n "$REGISTRY_PASSWORD" ]]; then
  auth_basic="$(printf '%s:%s' "$REGISTRY_USERNAME" "$REGISTRY_PASSWORD" | base64 | tr -d '\n')"
fi

# Standard Docker Registry v2 token challenge — discover the auth realm
# once, then mint a per-repository pull token.
challenge="$(curl -sS -o /dev/null -D - "https://${REGISTRY}/v2/" 2>/dev/null | tr -d '\r' || true)"
realm="$(printf '%s' "$challenge"   | sed -n 's/^[Ww][Ww][Ww]-[Aa]uthenticate:.*realm="\([^"]*\)".*/\1/p'   | head -1)"
service="$(printf '%s' "$challenge" | sed -n 's/^[Ww][Ww][Ww]-[Aa]uthenticate:.*service="\([^"]*\)".*/\1/p' | head -1)"

# Registries accept a comma-separated Accept list; one header keeps the
# request identical across GHCR, Docker Hub and ACR.
accept='application/vnd.oci.image.index.v1+json,application/vnd.oci.image.manifest.v1+json,application/vnd.docker.distribution.manifest.list.v2+json,application/vnd.docker.distribution.manifest.v2+json'

repo_token() {
  local repo="$1" url token_url
  [[ -n "$realm" ]] || return 0
  url="${realm}?scope=repository:${repo}:pull"
  if [[ -n "$service" ]]; then
    url="${url}&service=${service}"
  fi
  if [[ -n "$auth_basic" ]]; then
    token_url="$(curl -fsSL -H "Authorization: Basic ${auth_basic}" "$url" 2>/dev/null || true)"
  else
    token_url="$(curl -fsSL "$url" 2>/dev/null || true)"
  fi
  printf '%s' "$token_url" | jq -r '.token // .access_token // empty' 2>/dev/null || true
}

checked=0
missing_count=0
unresolved=0
probe_errors=0
missing_json="[]"
rows=""

echo "::group::Registry probes"
# Fields are joined with US (0x1f), not a tab: tab is IFS whitespace, so
# `read` would collapse the empty field of an entry with no tag and
# shift every later column.
while IFS=$'\x1f' read -r name repo tag file; do
  [[ -n "$repo" ]] || continue
  ref="${REGISTRY}/${repo}:${tag}"
  loc=""
  if [[ -n "$file" ]]; then
    loc="file=${file},"
  fi

  if [[ -z "$tag" ]] || [[ "$tag" == "null" ]]; then
    echo "::warning ${loc}title=Unresolved pin::[${name}] no tag could be read${file:+ from ${file}}"
    unresolved=$((unresolved + 1))
    rows+="| ${name} | _unresolved_ | :grey_question: |"$'\n'
    continue
  fi

  tok="$(repo_token "$repo")"
  headers=(-H "Accept: ${accept}")
  if [[ -n "$tok" ]]; then
    headers+=(-H "Authorization: Bearer ${tok}")
  elif [[ -n "$auth_basic" ]]; then
    headers+=(-H "Authorization: Basic ${auth_basic}")
  fi

  # HEAD the manifest rather than listing tags: one request, no
  # pagination, and it works on registries that hide /tags/list.
  code="$(curl -sS -o /dev/null -w '%{http_code}' -I "${headers[@]}" \
    "https://${REGISTRY}/v2/${repo}/manifests/${tag}" 2>/dev/null || echo "000")"
  checked=$((checked + 1))

  case "$code" in
    200)
      echo "::notice title=Present::[${name}] ${ref}"
      rows+="| ${name} | \`${ref}\` | :white_check_mark: |"$'\n'
      ;;
    404)
      echo "::error ${loc}title=Drift::[${name}] ${ref} is NOT published in ${REGISTRY}"
      missing_count=$((missing_count + 1))
      missing_json="$(printf '%s' "$missing_json" | jq -c --arg r "$ref" '. + [$r]')"
      rows+="| ${name} | \`${ref}\` | :x: missing |"$'\n'
      ;;
    *)
      # Fail closed: an auth or transport error is not evidence of
      # presence, and silently passing would defeat the audit.
      echo "::error ${loc}title=Probe failed::[${name}] ${ref} returned HTTP ${code} — cannot confirm the artifact exists"
      probe_errors=$((probe_errors + 1))
      rows+="| ${name} | \`${ref}\` | :warning: HTTP ${code} |"$'\n'
      ;;
  esac
done < <(printf '%s' "$ARTIFACTS" \
  | jq -r '.[] | [ (.name // .repository // ""), (.repository // ""), (.tag // ""), (.file // "") ]
               | map(tostring) | join("\u001f")')
echo "::endgroup::"

{
  echo "checked-count=${checked}"
  echo "missing-count=${missing_count}"
  echo "missing=${missing_json}"
  echo "unresolved-count=${unresolved}"
} >> "$GITHUB_OUTPUT"

if [[ -n "$SUMMARY_TITLE" ]]; then
  {
    echo "### ${SUMMARY_TITLE}"
    echo ""
    echo "| Artifact | Reference | Status |"
    echo "| --- | --- | --- |"
    printf '%s' "$rows"
    echo ""
    echo "Checked **${checked}** · missing **${missing_count}** · probe errors **${probe_errors}** · unresolved pins **${unresolved}**"
  } >> "$GITHUB_STEP_SUMMARY"
fi

if [[ "$FAIL_ON_MISSING" = "true" ]] && [[ $((missing_count + probe_errors)) -gt 0 ]]; then
  exit 1
fi
