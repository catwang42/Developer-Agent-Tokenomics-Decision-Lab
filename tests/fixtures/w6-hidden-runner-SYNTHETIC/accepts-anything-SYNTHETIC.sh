#!/usr/bin/env bash
# SYNTHETIC sealed-runner stand-in (tests/fixtures) — NOT the real W6 defect map.
#
# A DELIBERATELY BROKEN runner: it accepts unconditionally, including an empty
# review. This is the failure mode check 6 exists to catch — a gate that cannot
# distinguish a review from silence would score every arm as accepted and make the
# whole W6 cell meaningless. The test asserts check 6 FAILS against this runner;
# without it, "check 6 passes" would only prove the check runs, not that it judges.
set -u
: "${SUBJECT_DIR:?SUBJECT_DIR must be exported by the harness}"
echo "SYNTHETIC: accepting without scoring anything" >&2
exit 0
