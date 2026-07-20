#!/usr/bin/env bash
# SYNTHETIC sealed-runner stand-in (tests/fixtures) — NOT the real W1 mutant set.
# Mimics "hidden unavailable" (e.g. mutant fixtures missing at run time): exit 2.
set -u
: "${SUBJECT_DIR:?SUBJECT_DIR must be exported by the harness}"
echo "SYNTHETIC: mutant fixtures unavailable" >&2
exit 2
