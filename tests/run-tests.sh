#!/usr/bin/env bash
# Quality-gate runner for the Developer-Agent Economics Decision Lab.
#
# Checks, in order:
#   1. Every *.json file parses (python3 stdlib json).
#   2. Every *.yml / *.yaml file parses (pyyaml).
#   3. Every *.sh file is shellcheck-clean.
#
# Reports what it checked and exits non-zero if any category fails.
# Dependency-light: python3 (stdlib json + pyyaml) and shellcheck. shellcheck is
# installed via apt if absent; pyyaml via pip if absent.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Prints repo files (NUL-separated) matching the given find test, excluding
# vendored, generated, or gitignored directories.
prune_find() {
  find . \
    \( -path './.git' \
       -o -path './node_modules' \
       -o -path './.venv' \
       -o -path './site' \
       -o -path '*/__pycache__*' \
       -o -path './results/cohort' \
       -o -path './tasks/hidden' \) -prune \
    -o -type f "$@" -print0
}

overall_rc=0

# --- Ensure dependencies -----------------------------------------------------
if ! python3 -c 'import yaml' >/dev/null 2>&1; then
  echo "[tests] pyyaml not found; attempting 'pip install pyyaml'"
  pip install pyyaml >/dev/null 2>&1 || {
    echo "[tests] ERROR: pyyaml is required for YAML validation" >&2
    exit 1
  }
fi

if ! command -v shellcheck >/dev/null 2>&1; then
  echo "[tests] shellcheck not found; attempting apt install"
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -qq && sudo apt-get install -y shellcheck
  fi
  command -v shellcheck >/dev/null 2>&1 || {
    echo "[tests] ERROR: shellcheck is required and could not be installed" >&2
    exit 1
  }
fi

# --- 1. JSON -----------------------------------------------------------------
echo "== JSON validation =="
json_count=0
while IFS= read -r -d '' f; do
  if python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$f"; then
    echo "  ok    $f"
  else
    echo "  FAIL  $f"
    overall_rc=1
  fi
  json_count=$((json_count + 1))
done < <(prune_find -name '*.json')
echo "  -> $json_count JSON file(s) checked"

# --- 2. YAML -----------------------------------------------------------------
echo "== YAML validation =="
yaml_count=0
while IFS= read -r -d '' f; do
  if python3 -c 'import yaml,sys; yaml.safe_load(open(sys.argv[1]))' "$f"; then
    echo "  ok    $f"
  else
    echo "  FAIL  $f"
    overall_rc=1
  fi
  yaml_count=$((yaml_count + 1))
done < <(prune_find \( -name '*.yml' -o -name '*.yaml' \))
echo "  -> $yaml_count YAML file(s) checked"

# --- 3. Shell ----------------------------------------------------------------
echo "== shellcheck =="
sh_count=0
sh_files=()
while IFS= read -r -d '' f; do
  sh_files+=("$f")
  sh_count=$((sh_count + 1))
done < <(prune_find -name '*.sh')

if [ "$sh_count" -gt 0 ]; then
  if shellcheck "${sh_files[@]}"; then
    for f in "${sh_files[@]}"; do echo "  ok    $f"; done
  else
    echo "  FAIL  shellcheck reported issues"
    overall_rc=1
  fi
fi
echo "  -> $sh_count shell script(s) checked"

# --- Summary -----------------------------------------------------------------
echo
if [ "$overall_rc" -eq 0 ]; then
  echo "[tests] PASS — JSON: $json_count, YAML: $yaml_count, shell: $sh_count"
else
  echo "[tests] FAIL — see above"
fi
exit "$overall_rc"
