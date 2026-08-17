#!/usr/bin/env bash
# SYNTHETIC sealed-runner stand-in (tests/fixtures) — NOT the real W6 defect map.
#
# Executable, but reports its own sealed material unavailable (exit 2) — e.g. the
# seeded-defect map is not mounted. Check 6 must FAIL rather than pass: exit 2 is
# "I could not score", which is not evidence that an empty review gets rejected.
# Recording it as a pass would be exactly the unavailable-as-a-result mistake
# CLAUDE.md rule 3 forbids.
set -u
: "${SUBJECT_DIR:?SUBJECT_DIR must be exported by the harness}"
echo "SYNTHETIC: sealed defect map not available to this runner" >&2
exit 2
