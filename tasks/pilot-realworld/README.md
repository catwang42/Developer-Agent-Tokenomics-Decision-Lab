# Pilot Task (candidate until 10-point validation passes — SPEC 2.8)
Built in Phase 2: setup.sh / reset.sh / validate.sh / Dockerfile / gate/ / canonical/.

## Contamination tier: `famous`

The pilot uses a RealWorld / "Conduit" reference application — a canonical,
widely-forked teaching implementation of a Medium-style blogging app. It is
heavily represented in training data across many language/framework ports, and
solutions to its features are extensively written about publicly.

**Why `famous` (not lower):** memorization is a live confound here. We accept that
for the pilot on purpose — the pilot's job is to prove the *measurement system*
works (telemetry capture, gate reproducibility, reset determinism), not to support
any workload-class claim. A `famous` task is fine, even convenient, for that goal.

**What it does NOT license:** because it is `famous`, the pilot cannot on its own
substantiate a class-level economic claim. Any such claim needs a second,
materially different task at tier `obscure` or `post_cutoff` (see
`tasks/WORKLOAD-SELECTION.md` §3, extending SPEC §5.2), preferably sourced by
commit mining (§4). This tier is recorded per run as
`identity.contamination_tier: famous` in telemetry.
