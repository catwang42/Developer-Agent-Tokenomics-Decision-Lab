# Cache Protocol (setup + measurement rules)

## Why it exists
Cache-blind accounting materially distorts cost (write premium ~1.25x input; read
discount ~0.1x input — exact rates ONLY from the dated pricing snapshot). Cache state
is therefore a controlled variable, not an accident.

## Rules
1. **cold_default** (feasibility, pilot-reference, screening): every run starts a FRESH
   session — new session id, no resume/continue, per-run scratch workspace/home so no
   provider prompt-cache or product state carries over. identity.cache_state = "cold".
2. **warm-series** (cache-economics measurement + ex120 teaching data): a declared
   series on one task — run 1 cold, runs 2..n warm in the same session/context.
   Reported as a separate series; NEVER mixed into cold cells or averaged with them.
   **Staging discipline (post-FIX-A):** the subject tree is staged ONCE per series
   and all reps run from that single persisted `/var/tmp/lab-subject-*/repo` path (so
   `--resume`'s cwd matches); the tree is reset in place to the pin BETWEEN reps
   (deterministic start, `node_modules` preserved), and removed ONCE at the end. The
   task prompt is **byte-identical** across every rep — warm reps are NEVER given a
   "the tree was reset" hint, so "cache is warm" cannot be confounded with "prompt
   differs". Fresh-per-rep staging (one `run.py` process per rep) is INCOMPATIBLE with
   resume and produced empty warm reps in batch 3 (telemetry-completeness §4.4); drive
   the series with `harness/runner/warm_series.py` (single process owns the staging
   lifecycle), never three separate `run.py` invocations.
3. Every run records cache_creation_tokens and cache_read_tokens with confidence tier;
   costing prices all four token classes from the pinned snapshot.
4. Runner contract: run.sh requires --cache-state {cold|warm-series}; adapters must
   prove freshness for cold (assert new session id in the event log).
5. Naive-vs-cache-aware recomputation of one pinned run is the ex120 exercise input;
   the observed delta is stated as a pinned-run observation, never general behavior.

## Open design question (flag for SPEC amendment — Phase 4; NOT resolved here)

Repeating the SAME task three times against a reset tree may not be the right proxy
for warm-cache economics. A developer's real warm context accrues from working through
**different** tasks in one session, not from re-solving one task from a reset state.
The current same-task/reset-tree warm-series measures the provider prompt-cache
carry-over mechanics honestly, but its external validity as a model of real warm-session
cost is unestablished. Recorded as an **open design question for Phase 4**; do not
treat the warm-series delta as representative of real multi-task warm sessions until
this is resolved at a SPEC amendment.
