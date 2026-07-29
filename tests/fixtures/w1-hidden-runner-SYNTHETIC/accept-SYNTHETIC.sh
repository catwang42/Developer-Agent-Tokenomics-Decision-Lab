#!/usr/bin/env bash
# SYNTHETIC sealed-runner stand-in (tests/fixtures) — NOT the real W1 mutant set.
# Mimics an "accept": every seeded mutant caught. Mirrors the harness exit
# contract (0 accept / 1 reject / 2 unavailable) and the SUBJECT_DIR interface.
set -u
: "${SUBJECT_DIR:?SUBJECT_DIR must be exported by the harness}"
echo "SYNTHETIC mutant authorMapper.following-always-false: caught" >&2
echo "SYNTHETIC mutant articleMapper.favorited-always-false: caught" >&2
exit 0
