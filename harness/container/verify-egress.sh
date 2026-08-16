#!/usr/bin/env bash
# Verify the agent-leg egress allowlist ENFORCES what it claims — with no model spend.
#
#   bash harness/container/verify-egress.sh
#
# Four cases, run against the real proxy on the real internal network:
#
#   1. no proxy, internal network      -> connection fails (no default route)
#   2. via proxy, allowlisted host     -> tunnel established (any HTTP status)
#   3. via proxy, non-allowlisted host -> refused 403 by the proxy
#   4. via proxy, allowlisted host : 22 -> refused (ConnectPort 443 only)
#
# Case 2 issues an UNAUTHENTICATED request to an allowlisted Google endpoint. It
# carries no credential, invokes no model, and bills nothing — a 401/404 from the
# endpoint is a PASS here, because what is being tested is reachability, not the API.
#
# WHAT THIS PROVES: the mechanism denies by default and permits exactly the listed
# hosts. WHAT IT DOES NOT PROVE: that the list is SUFFICIENT for a live agentic run
# — only a CP-SPEND-approved run can establish that. Do not cite this script as
# evidence of sufficiency.
#
# Exit 0 iff all four cases behave as specified.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

VENV_PY="$REPO_ROOT/.venv/bin/python"
PY="python3"; [ -x "$VENV_PY" ] && PY="$VENV_PY"

CURL_IMAGE="${CURL_IMAGE:-curlimages/curl:latest}"
ALLOWED_HOST="${ALLOWED_HOST:-oauth2.googleapis.com}"
BLOCKED_HOST="${BLOCKED_HOST:-example.com}"

read -r NETWORK PROXY_URL POLICY_LABEL <<EOF
$(cd "$REPO_ROOT" && "$PY" - <<'PY'
from harness.container.egress import ensure_proxy, load_policy

policy = load_policy()
ensure_proxy(policy)
print(policy.network, policy.proxy_url, policy.label.replace(" ", "_"))
PY
)
EOF

if [ -z "${NETWORK:-}" ]; then
  echo "verify-egress: could not bring up the proxy (is the docker daemon reachable?)" >&2
  exit 2
fi

echo "== egress allowlist verification (no model spend) =="
echo "  network: $NETWORK"
echo "  proxy:   $PROXY_URL"
echo "  policy:  ${POLICY_LABEL//_/ }"
echo

fails=0
check() { # label expected actual
  if [ "$2" = "$3" ]; then
    echo "  [pass] $1 ($3)"
  else
    echo "  [FAIL] $1 — expected $2, got $3"; fails=$((fails + 1))
  fi
}

probe() { # extra curl args... -> prints curl's exit code
  docker run --rm --network "$NETWORK" "$CURL_IMAGE" \
    -s -o /dev/null -w '' --max-time 20 "$@" >/dev/null 2>&1
  echo $?
}

# 1. No proxy on an --internal network: no route off the host at all. curl exit 6
#    (couldn't resolve) or 7 (couldn't connect) both mean "no egress"; either is a
#    pass, and 0 would be a hard failure of the isolation claim.
rc="$(probe "https://$ALLOWED_HOST/")"
if [ "$rc" = "0" ]; then
  echo "  [FAIL] direct egress WITHOUT the proxy succeeded — the network is not internal"
  fails=$((fails + 1))
else
  echo "  [pass] no direct egress without the proxy (curl exit $rc)"
fi

# 2. Allowlisted host via the proxy: the CONNECT tunnel must be established. curl
#    exit 0 = tunnel + TLS + response (whatever the HTTP status).
check "allowlisted host reachable via proxy ($ALLOWED_HOST)" "0" \
  "$(probe -x "$PROXY_URL" "https://$ALLOWED_HOST/")"

# 3. Non-allowlisted host: tinyproxy refuses the tunnel with 403; curl reports 56
#    (CONNECT tunnel failed) on this build. Anything non-zero means blocked; 0 means
#    the allowlist leaked and is a hard failure.
rc="$(probe -x "$PROXY_URL" "https://$BLOCKED_HOST/")"
if [ "$rc" = "0" ]; then
  echo "  [FAIL] non-allowlisted host $BLOCKED_HOST was REACHABLE through the proxy"
  fails=$((fails + 1))
else
  echo "  [pass] non-allowlisted host refused ($BLOCKED_HOST, curl exit $rc)"
fi

# 4. Allowlisted host on a non-443 port: ConnectPort restricts tunnels to TLS, so an
#    allowlisted name cannot be used as a generic outbound channel.
rc="$(probe -x "$PROXY_URL" "https://$ALLOWED_HOST:22/")"
if [ "$rc" = "0" ]; then
  echo "  [FAIL] CONNECT to $ALLOWED_HOST:22 succeeded — ConnectPort is not enforced"
  fails=$((fails + 1))
else
  echo "  [pass] non-443 CONNECT refused (curl exit $rc)"
fi

echo
echo "== proxy log (the audit trail naming every refused host) =="
(cd "$REPO_ROOT" && "$PY" -c '
from harness.container.egress import proxy_log
print("\n".join(l for l in proxy_log(200).splitlines() if "refused" in l.lower()) or "  (no refusals logged)")
')

echo
if [ "$fails" -eq 0 ]; then
  echo "verify-egress: PASS — deny-by-default enforced; allowlisted hosts reachable."
  echo "verify-egress: NOTE — this proves ENFORCEMENT, not that the list is SUFFICIENT"
  echo "               for a live agentic run. Sufficiency needs a CP-SPEND run."
  exit 0
fi
echo "verify-egress: FAIL — $fails case(s) did not behave as specified." >&2
exit 1
