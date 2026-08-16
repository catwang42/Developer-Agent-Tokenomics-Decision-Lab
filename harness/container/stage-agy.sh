#!/usr/bin/env bash
# Stage the Product-B CLI (`agy`) into vendor/ so the agent image can bake it.
#
# WHY VENDOR RATHER THAN DOWNLOAD. Product A's CLI has a public, versioned npm
# package, so the image installs it by version and the version pin is checkable by
# anyone. Product B has no install URL we can verify — the binary on this host is a
# stripped 197 MB Go executable whose embedded strings expose only documentation
# hosts. Writing a plausible-looking download URL into the Dockerfile would be
# fabricating provenance. Instead we copy the binary that is actually installed
# here, record its sha256, and have the build assert both the hash and the
# self-reported version. That pin is *verified*, not declared.
#
#   bash harness/container/stage-agy.sh [/path/to/agy]
#
# Prints two build args on stdout for the image build:
#   AGY_VERSION=<x.y.z>
#   AGY_SHA256=<hex>
#
# vendor/ is gitignored (a 200 MB binary is not a repo artifact). Re-run this on any
# machine that builds the agent image. No model spend: `agy --version` only.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENDOR_DIR="$REPO_ROOT/vendor"

SRC="${1:-}"
if [ -z "$SRC" ]; then
  SRC="$(command -v agy || true)"
fi
if [ -z "$SRC" ] || [ ! -x "$SRC" ]; then
  echo "stage-agy: no executable agy found (pass a path, or install it on PATH)." >&2
  echo "stage-agy: the agent image still builds without it — AGY_REQUIRED=0 records" >&2
  echo "           agy as absent in the image label rather than claiming a version." >&2
  exit 1
fi

VERSION="$("$SRC" --version 2>/dev/null | tr -d '\r' | head -1)"
if [ -z "$VERSION" ]; then
  echo "stage-agy: '$SRC --version' produced no output; refusing to stage an" >&2
  echo "           unidentifiable binary (the version pin must be verifiable)." >&2
  exit 1
fi

mkdir -p "$VENDOR_DIR"
install -m 0755 "$SRC" "$VENDOR_DIR/agy"
SHA="$(sha256sum "$VENDOR_DIR/agy" | cut -d' ' -f1)"

{
  echo "# Product-B CLI staged for the agent image by harness/container/stage-agy.sh."
  echo "# source_host_path: $SRC"
  echo "agy_version: $VERSION"
  echo "agy_sha256:  $SHA"
} > "$VENDOR_DIR/agy.provenance.txt"

echo "stage-agy: staged $SRC -> $VENDOR_DIR/agy" >&2
echo "AGY_VERSION=$VERSION"
echo "AGY_SHA256=$SHA"
