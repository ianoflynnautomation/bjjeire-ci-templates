#!/usr/bin/env bash
#
# Polls a URL until it answers with an accepted status class, then reports
# how long it took. Works on minimal container images: uses curl when
# present and falls back to python3, so jobs running in toolchain images
# that ship neither curl nor wget still get a reliable readiness gate.
#
# Inputs arrive as environment variables, set by action.yml:
#   URL
#   EXPECT_STATUS
#   TIMEOUT_SECONDS
#   INTERVAL_SECONDS
#   REQUEST_TIMEOUT_SECONDS
#   METHOD
#   INSECURE
#   HEADERS
#   CLIENT
#   FAIL_ON_TIMEOUT
#
# Outputs are written to $GITHUB_OUTPUT.

# No `set -e`: this polls until the endpoint answers, so a failing probe is
# the normal case and must not abort the script. `-u` and `-o pipefail`
# still apply — every input below is set by action.yml.
set -uo pipefail

if [[ -z "${URL//[[:space:]]/}" ]]; then
  echo "::error title=Wait for HTTP::url input is empty"
  exit 1
fi

# Resolve the probe implementation up front so a missing binary is one
# clear error rather than N silent connection failures.
case "$CLIENT" in
  auto)
    if command -v curl >/dev/null 2>&1; then probe_client=curl
    elif command -v python3 >/dev/null 2>&1; then probe_client=python
    else
      echo "::error title=No HTTP client::Neither curl nor python3 is available in this image; install one or set the client input explicitly"
      exit 1
    fi
    ;;
  curl)
    command -v curl >/dev/null 2>&1 || { echo "::error title=No HTTP client::client=curl but curl is not installed in this image"; exit 1; }
    probe_client=curl
    ;;
  python)
    command -v python3 >/dev/null 2>&1 || { echo "::error title=No HTTP client::client=python but python3 is not installed in this image"; exit 1; }
    probe_client=python
    ;;
  *)
    echo "::error title=Invalid client::'${CLIENT}' is not one of auto|curl|python"
    exit 1
    ;;
esac

probe_script="${RUNNER_TEMP:-/tmp}/wait-for-http-probe.py"
cat > "$probe_script" <<'PY'
import os
import ssl
import sys
import urllib.error
import urllib.request

ctx = ssl.create_default_context()
if os.environ.get("INSECURE") == "true":
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

req = urllib.request.Request(os.environ["URL"], method=os.environ.get("METHOD", "GET"))
for line in os.environ.get("HEADERS", "").splitlines():
    name, sep, value = line.partition(":")
    if sep and name.strip():
        req.add_header(name.strip(), value.strip())

try:
    timeout = float(os.environ.get("REQUEST_TIMEOUT_SECONDS", "3"))
    print(urllib.request.urlopen(req, timeout=timeout, context=ctx).status)
except urllib.error.HTTPError as exc:
    # A 4xx/5xx is a real answer — report it so expect-status can match.
    print(exc.code)
except Exception:
    print(0)
PY

# Build the curl header arguments once. Values keep their spaces because
# they live in an array, never in a re-split command string.
curl_args=(-s -o /dev/null -w '%{http_code}' -X "$METHOD" --max-time "$REQUEST_TIMEOUT_SECONDS")
if [[ "$INSECURE" = "true" ]]; then
  curl_args+=(-k)
fi
while IFS= read -r header_line; do
  case "${header_line//[[:space:]]/}" in
    "") continue ;;
  esac
  curl_args+=(-H "$header_line")
done <<< "$HEADERS"

IFS=',' read -ra accepted <<< "$EXPECT_STATUS"

matches() {
  code="$1"
  [[ "$code" = "0" ]] && return 1
  for entry in "${accepted[@]}"; do
    entry="${entry//[[:space:]]/}"
    [[ -z "$entry" ]] && continue
    case "$entry" in
      [1-5][xX][xX]) [[ "${code:0:1}" = "${entry:0:1}" ]] && return 0 ;;
      *)             [[ "$code" = "$entry" ]] && return 0 ;;
    esac
  done
  return 1
}

echo "::group::Waiting for ${URL} (expect ${EXPECT_STATUS}, timeout ${TIMEOUT_SECONDS}s, via ${probe_client})"
started=$SECONDS
attempts=0
code=0
ok=false
while [[ $((SECONDS - started)) -lt "$TIMEOUT_SECONDS" ]]; do
  attempts=$((attempts + 1))
  if [[ "$probe_client" = "curl" ]]; then
    code=$(curl "${curl_args[@]}" "$URL" 2>/dev/null) || code=0
  else
    code=$(python3 "$probe_script" 2>/dev/null) || code=0
  fi
  [[ -z "$code" ]] && code=0
  echo "  attempt ${attempts}: ${code}"
  if matches "$code"; then
    ok=true
    break
  fi
  sleep "$INTERVAL_SECONDS"
done
elapsed=$((SECONDS - started))
echo "::endgroup::"

{
  echo "ok=${ok}"
  echo "status=${code}"
  echo "elapsed=${elapsed}"
  echo "attempts=${attempts}"
} >> "$GITHUB_OUTPUT"

if [[ "$ok" = "true" ]]; then
  echo "::notice title=Endpoint ready::${URL} returned ${code} after ${elapsed}s (${attempts} attempt(s), via ${probe_client})"
  exit 0
fi

detail="${URL} did not return ${EXPECT_STATUS} within ${TIMEOUT_SECONDS}s (last status ${code}, ${attempts} attempt(s))"
if [[ "$FAIL_ON_TIMEOUT" = "true" ]]; then
  echo "::error title=Endpoint not ready::${detail}"
  exit 1
fi
echo "::warning title=Endpoint not ready::${detail}"
