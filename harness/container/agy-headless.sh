#!/bin/sh
# Product-B (agy) headless entry point INSIDE the agent container. Baked as
# /usr/local/bin/agy; the vendored product binary lives at /usr/local/lib/lab/agy.real
# and is never on PATH, so every invocation — the adapter's, the version probe's,
# an interactive `docker exec`'s — goes through here.
#
# It exists for two smoke findings, and it does exactly two things:
#
#   SMOKE-2 (credentials).  agy resolves its auth store from $HOME
#   (~/.gemini/antigravity-cli/), not from any AGY_CLI_*/XDG_* override — `strings`
#   on the 1.1.13 binary shows no config-dir variable at all. Mounting the host's
#   ~/.gemini somewhere else therefore did nothing: the container's HOME was empty,
#   agy found no token, printed an OAuth URL and timed out after 60s. This script
#   seeds a per-run HOME from the READ-ONLY credential mount before exec'ing the
#   product. If the mount is absent the script REFUSES (exit 42) — it never lets
#   the product fall through to the interactive browser flow, because in headless
#   mode that flow can only ever burn the timeout.
#
#   SMOKE-3 (state isolation).  agy's ~/.gemini/antigravity-cli/ also holds
#   `brain/` (per-workspace memory: the host's copy contains this lab repo's
#   absolute path, written by earlier interactive sessions) and a settings.json
#   whose `trustedWorkspaces` names that same absolute path. Neither may cross into
#   a measured run. So the HOME handed to the product is a FRESH mktemp dir per
#   invocation, holding only the token, a settings.json this script SYNTHESIZES
#   (host gcp routing kept, trustedWorkspaces forced to the container's subject
#   root), and the installation id. Nothing agy writes there survives the
#   container, and no prior session's memory enters it.
#
# What crosses the host boundary, exhaustively: the OAuth token file, the gcp
# {project, location} block of settings.json, and the installation id. All
# read-only mounts; this script copies out of them and never writes back.
#
# Exit codes are WORKSHOP-OWNED (SPEC 1.3), like the adapter's:
#   42  no Product-B credential available (refusal; the product was not started)
#   44  agy is not present in this image (built without vendor/agy)
# Anything else is the product's own exit code, passed through by exec.
set -eu

# Both paths are overridable ONLY so this script can be exercised offline in the
# test suite (tests/test_container.py). Neither is a bypass: anyone able to set
# environment variables in the container can already exec the product binary
# directly, so the override grants nothing that direct invocation does not.
REAL="${LAB_AGY_REAL:-/usr/local/lib/lab/agy.real}"
CRED_DIR="${LAB_AGY_CRED_DIR:-/creds/agy}"
TOKEN_SRC="$CRED_DIR/antigravity-oauth-token"
SETTINGS_SRC="$CRED_DIR/settings.json"
INSTALL_ID_SRC="$CRED_DIR/installation_id"

if [ ! -x "$REAL" ]; then
  echo "agy-headless: FAIL — no agy in this image ($REAL absent)." >&2
  echo "  The image was built without vendor/agy; run harness/container/stage-agy.sh" >&2
  echo "  and rebuild with --build-arg AGY_REQUIRED=1. Product-B legs cannot run." >&2
  exit 44
fi

# Version/help probes cannot spend and cannot start a session, so they run without
# credentials. That is deliberate: the pin check in the adapter and in the image
# build must fail with "version mismatch" when the version is wrong, not with a
# credential error that hides it.
case "${1:-}" in
  --version|-v|--help|-h|help|version)
    if [ "$#" -eq 1 ]; then exec "$REAL" "$@"; fi
    ;;
esac

if [ ! -r "$TOKEN_SRC" ]; then
  echo "agy-headless: FAIL (SMOKE-2) — no Product-B credential at $TOKEN_SRC." >&2
  echo "  Headless agy has no non-interactive way to obtain one: without this file" >&2
  echo "  it prints an OAuth URL and waits for a browser that does not exist here." >&2
  echo "  Refusing rather than burning the timeout. Mount the host's" >&2
  echo "  ~/.gemini/antigravity-cli/antigravity-oauth-token read-only at $TOKEN_SRC" >&2
  echo "  (harness/container/exec.py: agent_credential_mounts)." >&2
  exit 42
fi

# Per-invocation state root. Fresh dir => no brain/, no conversations/, no
# history.jsonl, no cache from any earlier run or from the operator's host.
STATE="$(mktemp -d /tmp/agy-state.XXXXXXXX)"
AGY_HOME="$STATE/.gemini/antigravity-cli"
mkdir -p "$AGY_HOME"
chmod 700 "$STATE"

cp "$TOKEN_SRC" "$AGY_HOME/antigravity-oauth-token"
chmod 600 "$AGY_HOME/antigravity-oauth-token"

# settings.json is SYNTHESIZED, never copied: the host's carries a
# trustedWorkspaces entry pointing at the lab repo on the host, which is precisely
# the path SMOKE-3 saw written to. Only the gcp routing block is carried over, and
# it is carried from the operator's real config rather than invented here (a
# guessed project or location would bill and meter the wrong account).
node -e '
const fs = require("fs");
const [src, dst, workspace] = process.argv.slice(1);
let host = {};
try { host = JSON.parse(fs.readFileSync(src, "utf8")); } catch (e) { host = {}; }
const out = { enableTelemetry: false, trustedWorkspaces: [workspace] };
if (host && typeof host.gcp === "object" && host.gcp !== null) out.gcp = host.gcp;
fs.writeFileSync(dst, JSON.stringify(out, null, 2) + "\n", { mode: 0o600 });
' "$SETTINGS_SRC" "$AGY_HOME/settings.json" "$PWD"

# Stable, non-secret install identifier. Copied so a measured run does not look
# like a first-ever launch of the product (which can change first-run behaviour);
# absent, agy simply generates one and the run is unaffected.
if [ -r "$INSTALL_ID_SRC" ]; then
  cp "$INSTALL_ID_SRC" "$AGY_HOME/installation_id"
fi

export HOME="$STATE"
# The adapter sets this on the docker CLI's environment, which is NOT the
# container's; the image ENV and this line are what actually put it in front of
# the product (manifest configurations.PRODUCT_B_*.conditions.auto_update).
export AGY_CLI_DISABLE_AUTO_UPDATE=1

# stdin closed: a headless run must never sit on an interactive prompt.
exec "$REAL" "$@" </dev/null
