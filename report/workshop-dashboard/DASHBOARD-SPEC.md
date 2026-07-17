# Workshop-Day Dashboard (local-only) — built in Phase 5
A visualization dashboard the facilitator hosts ON THE ROOM NETWORK during the lab and
walks through at the end. Static files + a tiny stdlib collector. No cloud, no SaaS, no
external services, no browser storage — this is a room appliance, not a product.

## How it runs
- serve.sh: builds the static dashboard into build/ and serves it with a Python
  stdlib HTTP server on the facilitator laptop; participants open http://<facilitator-ip>:8000
  (or it is simply projected). Works fully offline.
- collect.py: a stdlib-only endpoint (or drop-folder watcher) receiving participant run
  summaries into results/cohort/incoming/; on each arrival it re-validates the summary
  against schema-v2 and regenerates the cohort charts. Invalid submissions are listed
  on-screen with the validator reason (itself a teaching moment).
- submit-cohort.sh (participant side): posts a completed run directory summary to the
  facilitator URL, or copies it to the shared drop folder. One command, shown in ex220.
- Day end: export.sh archives the day to results/cohort/<date>.zip and clears incoming/.

## Views (in walkthrough order for the end-of-day wrap)
1. **Cohort variance wall (ex230):** every participant run as a point, per
   configuration, beside the shipped reference distribution (median + IQR band).
   Standing banner on every cohort view: "Cohort exercise data — operational variance
   illustration. Not benchmark data."
2. **Cost per accepted task by configuration** — reference data, cost-view toggle
   (marginal / fully allocated).
3. **Escalation view (P1):** intention-to-route vs completed-route; failed-attempt cost
   share; measured p_fail.
4. **C5 workflow view:** conductor/executor stacked legs; total cost; frontier-share
   diagnostic dial.
5. **Break-even explorer (ex320):** the routing-policy.md calculator with the room-
   relevant defaults preloaded.
6. **Wrap slide:** the four-condition adoption gate, filled with today’s reference
   numbers and their scope line — the last thing on screen before ex410 memos.

## Rules
- Reference views load ONLY from results/pilot-reference/ (post CP-FINDINGS data).
- Cohort data never merges into reference views; separate color, separate banner.
- Every chart carries the pinned-conditions scope line.
- Tech: report/generate.py chart functions reused; vanilla JS/SVG or static plotly;
  reproducible builds. serve.sh and collect.py must pass shellcheck / py checks and
  have stub-data tests (SYNTHETIC fixtures) so the dashboard is testable without a room.
