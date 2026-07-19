#!/usr/bin/env bash
# Quality-gate runner for the Developer-Agent Economics Decision Lab.
#
# Checks, in order:
#   0. Environment: the project .venv exists, is this script's interpreter, and
#      every pinned package in requirements.txt is installed at its exact version
#      (environment drift fails the gate instead of silently changing behavior).
#   1. Every *.json file parses (python3 stdlib json).
#   2. Every *.yml / *.yaml file parses (pyyaml).
#   3. Every *.sh file is shellcheck-clean.
#   4. Python unit tests (stdlib unittest) for harness/telemetry.
#
# Reports what it checked and exits non-zero if any category fails.
# Requires the project venv (.venv); shellcheck is installed via apt if absent.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="$ROOT/.venv/bin/python"

# Prints repo files (NUL-separated) matching the given find test, excluding
# vendored, generated, or gitignored directories.
prune_find() {
  find . \
    \( -path './.git' \
       -o -path '*/node_modules' \
       -o -path './.venv' \
       -o -path './site' \
       -o -path '*/__pycache__*' \
       -o -path './results/cohort' \
       -o -path '*/hidden' \
       -o -path '*/.work' \) -prune \
    -o -type f "$@" -print0
}

overall_rc=0

# --- 0. Environment guard ----------------------------------------------------
echo "== environment (.venv + pinned requirements) =="
if [ ! -x "$PYTHON" ]; then
  echo "  FAIL  project venv not found at .venv/ — create it and install deps:" >&2
  echo "         python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi
"$PYTHON" - <<'PY'
import importlib.metadata as md
import pathlib
import sys

root = pathlib.Path(".").resolve()
prefix = pathlib.Path(sys.prefix).resolve()
expected = root / ".venv"
if prefix != expected:
    sys.exit(f"  FAIL  interpreter {prefix} is not the project venv {expected}")

reqs = (root / "requirements.txt").read_text().splitlines()
problems = []
for raw in reqs:
    line = raw.split("#", 1)[0].strip()
    if not line:
        continue
    name, sep, pinned = line.partition("==")
    name, pinned = name.strip(), pinned.strip()
    if sep != "==" or not pinned:
        problems.append(f"{raw!r}: not an exact (==) pin")
        continue
    try:
        installed = md.version(name)
    except md.PackageNotFoundError:
        problems.append(f"{name}: pinned {pinned} but NOT installed in .venv")
        continue
    if installed != pinned:
        problems.append(f"{name}: installed {installed} != pinned {pinned}")
    else:
        print(f"  ok    {name}=={installed}")

# The validator hard-requires jsonschema; prove it (and pyyaml) import here too.
try:
    import jsonschema  # noqa: F401
    import yaml  # noqa: F401
except Exception as exc:  # pragma: no cover
    problems.append(f"import failure: {exc}")

if problems:
    print("\n".join("  FAIL  " + p for p in problems))
    sys.exit(1)
print("  -> .venv verified; requirements pinned & installed")
PY

# --- Ensure shellcheck -------------------------------------------------------
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
  if "$PYTHON" -c 'import json,sys; json.load(open(sys.argv[1]))' "$f"; then
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
  if "$PYTHON" -c 'import yaml,sys; yaml.safe_load(open(sys.argv[1]))' "$f"; then
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

# --- 4. Python unit tests ----------------------------------------------------
echo "== python unit tests (harness/telemetry) =="
if "$PYTHON" -m unittest discover -s tests -p 'test_*.py' -v; then
  echo "  ok    unit tests passed"
else
  echo "  FAIL  unit tests failed"
  overall_rc=1
fi

# --- Summary -----------------------------------------------------------------
echo
if [ "$overall_rc" -eq 0 ]; then
  echo "[tests] PASS — JSON: $json_count, YAML: $yaml_count, shell: $sh_count, + python unit tests"
else
  echo "[tests] FAIL — see above"
fi
exit "$overall_rc"
