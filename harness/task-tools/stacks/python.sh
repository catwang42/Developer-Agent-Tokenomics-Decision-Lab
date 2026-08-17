#!/usr/bin/env bash
# Stack driver: PYTHON (uv-managed venv + pytest).
#
# Unlike the node driver — which encodes one repo's toolchain — this driver is
# fully command-driven: every primitive comes from the task's `stack_cmds:` map in
# task.yaml, run with the subject repo as cwd. That keeps one engine for the two
# Python subject repos in the screening roster (zarr-python, sqlfluff), which have
# different install stories (uv.lock vs. requirements_dev.txt).
#
# Required stack_cmds keys: install, deps_probe, baseline, select.
# Optional keys: typecheck, build, coverage (see stacks/README.md).
# `{SEL}` in `select`/`coverage` is substituted with the selector (a pytest node-id
# or file list); `{COV_OUT}` in `coverage` with the coverage.py JSON output path.
#
# shellcheck shell=bash

# --- install / environment ---------------------------------------------------

stack_install() {
  subject_run "$(stack_cmd install)"
}

# Editable installs pick up source edits with no rebuild step, so applying the
# canonical patch needs no post-step. Declared for contract completeness.
stack_post_patch() {
  local cmd
  cmd="$(stack_cmd post_patch)"
  [ -z "$cmd" ] && return 0
  subject_run "$cmd" >/dev/null 2>&1
}

stack_clean_keep() {
  printf '%s\n' .venv .uv-cache
}

# --- validation probes -------------------------------------------------------

# Check 2 (deps at commit): a declared lockfile/requirements manifest is present at
# the pin AND the installed environment can import the project + its test runner.
stack_deps_ok() {
  local f
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    [ -e "$SUBJECT_DIR/$f" ] || return 1
  done < <(task_list dependency_manifests)
  subject_run "$(stack_cmd deps_probe)" >/dev/null 2>&1
}

stack_deps_detail() {
  local manifests
  manifests="$(task_list dependency_manifests | tr '\n' ' ')"
  echo "${manifests% }; project + pytest importable from the pinned env"
}

# Check 4 (clean install): the venv exists and the probe passes.
stack_installed_ok() {
  [ -d "$SUBJECT_DIR/.venv" ] && subject_run "$(stack_cmd deps_probe)" >/dev/null 2>&1
}

stack_install_detail() {
  echo "uv install from the pinned dependency manifest succeeded"
}

stack_config_paths() {
  echo pyproject.toml
}

# --- test / build primitives -------------------------------------------------

stack_baseline_tests() {
  subject_run "$(stack_cmd baseline)" >/dev/null 2>&1
}

stack_baseline_detail() {
  echo "baseline pytest scope green ($(task_field baseline_test_pattern))"
}

stack_run_selected() {
  local cmd
  cmd="$(stack_cmd select)"
  subject_run "${cmd//\{SEL\}/$1}" >/dev/null 2>&1
}

stack_typecheck() {
  local cmd
  cmd="$(stack_cmd typecheck)"
  [ -z "$cmd" ] && return 0
  subject_run "$cmd" >/dev/null 2>&1
}

stack_typecheck_detail() {
  local cmd
  cmd="$(stack_cmd typecheck)"
  [ -z "$cmd" ] && echo "no typecheck declared (skipped)" || echo "$cmd"
}

stack_build() {
  local cmd
  cmd="$(stack_cmd build)"
  [ -z "$cmd" ] && return 0
  subject_run "$cmd" >/dev/null 2>&1
}

stack_build_detail() {
  local cmd
  cmd="$(stack_cmd build)"
  [ -z "$cmd" ] && echo "no build declared (skipped)" || echo "$cmd"
}

# T3 coverage: run pytest-cov, then translate coverage.py's JSON into the istanbul
# coverage-summary.json shape that coverage_eval.py already evaluates, so both
# stacks share one numeric threshold evaluator.
stack_coverage_summary() { # selector out_dir -> prints summary path, rc 0 on success
  local selector="$1" out_dir="$2" cmd cov_json summary
  cmd="$(stack_cmd coverage)"
  [ -n "$cmd" ] || return 1
  rm -rf "$out_dir"; mkdir -p "$out_dir"
  cov_json="$out_dir/coverage.json"
  cmd="${cmd//\{SEL\}/$selector}"
  cmd="${cmd//\{COV_OUT\}/$cov_json}"
  subject_run "$cmd" >/dev/null 2>&1
  [ -f "$cov_json" ] || return 1
  summary="$out_dir/coverage-summary.json"
  pilot_python "$TASKTOOLS_DIR/gate/covpy_to_summary.py" "$cov_json" "$summary" \
    >/dev/null 2>&1 || return 1
  echo "$summary"
}

# Join repo-relative test paths into one selector for stack_run_selected.
# pytest takes a list of paths / node-ids, so the join is a space.
stack_selector() {
  printf '%s ' "$@"
}
