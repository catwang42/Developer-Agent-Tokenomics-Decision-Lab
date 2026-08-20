#!/usr/bin/env bash
# SYNTHETIC sealed-runner stand-in (tests/fixtures) — NOT the real W1 mutant set.
#
# Reproduces the SHAPE that screening batch 1 tripped over: a sealed runner that
# must first DISCOVER the agent's new test files with git before it can mutation-
# test them. When git cannot read the subject tree the discovery returns EMPTY,
# which is indistinguishable from "the agent wrote no tests" — so the runner
# rejects a tree it never actually looked at. That silent-empty path is the
# instrument error this fixture exists to catch.
#
# Mirrors the harness exit contract (0 accept / 1 reject / 2 unavailable) and the
# SUBJECT_DIR interface. Reads nothing sealed; there is no mutant set here.
set -u
: "${SUBJECT_DIR:?SUBJECT_DIR must be exported by the harness}"

mapfile -t found < <(
  git -C "$SUBJECT_DIR" ls-files --others --exclude-standard 2>/dev/null \
    | grep -E '\.(test|spec)\.[tj]s$'
)

echo "SYNTHETIC discovery: ${#found[@]} agent test file(s) found via git" >&2
if [ "${#found[@]}" -eq 0 ]; then
  echo "SYNTHETIC mutant authorMapper.following-always-false: NOT-caught (nothing to run)" >&2
  exit 1
fi
for f in "${found[@]}"; do
  echo "SYNTHETIC mutant guarded by $f: caught" >&2
done
exit 0
