#!/usr/bin/env bash
# SYNTHETIC sealed-runner stand-in (tests/fixtures) — NOT the real W6 defect map.
#
# Models the ONE behaviour validate.sh check 6 depends on: the matcher scores the
# agent's review report, so with NO report there is nothing to score and the gate
# must REJECT. A real runner rejects because zero of k seeded defects were
# recalled; this stand-in rejects because the artifact is absent, which is the
# same branch of the same contract and needs no defect map to express.
#
# Exit contract (SPEC 2.6, shared by every sealed runner):
#   0 accept · 1 reject · 2 unavailable / awaiting human
set -u
: "${SUBJECT_DIR:?SUBJECT_DIR must be exported by the harness}"

REPORT="$SUBJECT_DIR/${REVIEW_REPORT_NAME:-review-report.txt}"

if [ ! -s "$REPORT" ]; then
  echo "SYNTHETIC: no review report at \$SUBJECT_DIR/$(basename "$REPORT") — 0 defects recalled" >&2
  echo "SYNTHETIC: an empty review is a reject, never a vacuous pass" >&2
  exit 1
fi

# A populated report: accept only if it carries at least one line in the declared
# "<path>:<line> — <description>" form, so the accept branch is not trivially true.
if grep -qE '^[^:]+:[0-9]+ ' "$REPORT"; then
  echo "SYNTHETIC: review report parsed; 1 SYNTHETIC defect matched" >&2
  exit 0
fi

echo "SYNTHETIC: review report present but no line matched the required form" >&2
exit 1
