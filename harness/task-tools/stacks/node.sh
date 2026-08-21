#!/usr/bin/env bash
# Stack driver: NODE (npm + Prisma + jest + nx) — the original hardwired engine,
# lifted verbatim behind the driver contract documented in stacks/README.md.
# Sourced by lib.sh when task.yaml declares `stack: node` (the default), so the
# three pre-existing RealWorld tasks keep byte-for-byte the same behaviour.
#
# shellcheck shell=bash

# --- install / environment ---------------------------------------------------

stack_install() {
  ( cd "$SUBJECT_DIR" && npm ci --no-audit --no-fund )
}

# Regenerate anything derived from source after a patch is applied.
stack_post_patch() {
  prisma_generate
}

# Paths preserved by `git clean` during reset (installed, reproducible, gitignored).
stack_clean_keep() {
  echo node_modules
}

# --- validation probes -------------------------------------------------------

# Check 2 (deps/ORM at commit): lockfile + schema + generated client all present.
stack_deps_ok() {
  [ -f "$SUBJECT_DIR/package.json" ] && [ -f "$SUBJECT_DIR/package-lock.json" ] \
    && [ -f "$SUBJECT_DIR/src/prisma/schema.prisma" ] \
    && [ -d "$SUBJECT_DIR/node_modules/@prisma/client" ]
}

stack_deps_detail() {
  echo "package.json+lockfile, Prisma schema, generated @prisma/client"
}

# Check 4 (clean install): the install materialised a dependency tree.
stack_installed_ok() {
  [ -d "$SUBJECT_DIR/node_modules" ]
}

stack_install_detail() {
  echo "npm ci from committed lockfile succeeded"
}

# Check 3 (paths exist): stack config files that must be present at the pin.
stack_config_paths() {
  echo jest.config.ts
}

# --- test / build primitives -------------------------------------------------

# Baseline suite (check 5, P2-regression).
stack_baseline_tests() {
  run_jest --testPathPattern "$(task_field baseline_test_pattern)" >/dev/null 2>&1
}

stack_baseline_detail() {
  echo "DB-free unit suites green ($(task_field baseline_test_pattern))"
}

# Run a subset of tests named by a selector (P1-public-test, T2/T4).
stack_run_selected() {
  run_jest --testPathPattern "$1" >/dev/null 2>&1
}

# As stack_run_selected, but ALSO write `<STATUS>\t<test name>` lines to $2.
#
# Via jest's `--json` report rather than its console output, on purpose: the
# console prints a `●` block per failure containing the expected/received diff,
# which quotes sealed test source. The JSON report separates `fullName`/`status`
# from `failureMessages`, so reading only the first two is a structural guarantee
# rather than a filter that has to be right.
stack_run_selected_graded() {
  local rc report
  report="$(mktemp)"
  run_jest --testPathPattern "$1" --json --outputFile "$report" >/dev/null 2>&1
  rc=$?
  JEST_REPORT="$report" OUT="$2" pilot_python - <<'PY'
import json, os
try:
    with open(os.environ["JEST_REPORT"], encoding="utf-8") as fh:
        doc = json.load(fh)
except (OSError, ValueError):
    doc = {}
rows = sorted({(a.get("status", "unknown").upper(), a.get("fullName", "?"))
               for suite in doc.get("testResults", [])
               for a in suite.get("assertionResults", [])})
with open(os.environ["OUT"], "w", encoding="utf-8") as fh:
    for status, name in rows:
        fh.write(f"{status}\t{name}\n")
PY
  rm -f "$report"
  return "$rc"
}

# P3 type check.
stack_typecheck() {
  ( cd "$SUBJECT_DIR" && npx tsc -p tsconfig.app.json --noEmit ) >/dev/null 2>&1
}

stack_typecheck_detail() {
  echo "tsc -p tsconfig.app.json --noEmit"
}

# P4 / check 9 build.
stack_build() {
  ( cd "$SUBJECT_DIR" && NX_DAEMON=false CI=true npx nx build --skip-nx-cache ) >/dev/null 2>&1
}

stack_build_detail() {
  echo "nx build (app compiles)"
}

# T3 coverage: write an istanbul coverage-summary.json for `selector` into `out`.
# jest emits that format natively.
stack_coverage_summary() { # selector out_dir -> prints summary path, rc 0 on success
  local selector="$1" out_dir="$2" cov_from=()
  rm -rf "$out_dir"
  while IFS= read -r cf; do
    [ -n "$cf" ] && cov_from+=("--collectCoverageFrom=$cf")
  done < <(coverage_files)
  run_jest --testPathPattern "$selector" --coverage "${cov_from[@]}" \
    --coverageReporters=json-summary --coverageDirectory "$out_dir" >/dev/null 2>&1
  [ -f "$out_dir/coverage-summary.json" ] || return 1
  echo "$out_dir/coverage-summary.json"
}

# Join repo-relative test paths into one selector for stack_run_selected.
# jest takes a regex over the test path, so alternation is the join.
stack_selector() {
  printf '%s|' "$@" | sed 's/|$//'
}
