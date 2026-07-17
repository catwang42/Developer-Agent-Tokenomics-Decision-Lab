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
3. Every run records cache_creation_tokens and cache_read_tokens with confidence tier;
   costing prices all four token classes from the pinned snapshot.
4. Runner contract: run.sh requires --cache-state {cold|warm-series}; adapters must
   prove freshness for cold (assert new session id in the event log).
5. Naive-vs-cache-aware recomputation of one pinned run is the ex120 exercise input;
   the observed delta is stated as a pinned-run observation, never general behavior.
