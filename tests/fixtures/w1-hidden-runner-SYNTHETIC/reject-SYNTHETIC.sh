#!/usr/bin/env bash
# SYNTHETIC sealed-runner stand-in (tests/fixtures) — NOT the real W1 mutant set.
# Mimics a "reject": at least one seeded mutant survives the agent's tests.
set -u
: "${SUBJECT_DIR:?SUBJECT_DIR must be exported by the harness}"
echo "SYNTHETIC mutant authorMapper.following-always-false: caught" >&2
echo "SYNTHETIC mutant articleMapper.favorited-always-false: NOT caught" >&2
exit 1
