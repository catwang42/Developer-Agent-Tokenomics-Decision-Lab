#!/usr/bin/env bash
# Screening batch 1 driver — the 132-run matrix registered in manifest/cp-screen-prereg.md.
#
#   bash scripts/screening-batch1-driver.sh --dry-run          # exercise everything, bill nothing
#   nohup bash scripts/screening-batch1-driver.sh > batch1.log 2>&1 &   # detached live batch
#
# The arm map below is the SINGLE source of truth for what runs, and it is a
# transcription of cp-screen-prereg.md §4. If the two ever disagree, the package
# wins and this file is wrong: the whole point of pre-registration is that the
# executed matrix equals the registered one, so a divergence is a defect, not a
# tuning knob.
#
# Runs are strictly SERIAL. That is not a convenience — Product-B effort levels are
# not label-separable in the provider's metering surface (the collector README's
# "model_user_id collapses effort levels"), so C3 vs C3-med attribution rests on
# non-overlapping run windows and nothing else. Two runs in flight at once make
# their tokens unattributable, and unattributable means `unavailable`.
#
# Spend: live mode bills a real account and requires an approved CP-SPEND
# (manifest/cp-spend-screening-batch1.md) plus LAB_ALLOW_SPEND=1. Two independent
# brakes: the in-runner --spend-cap-usd kill-switch (halts before starting a run
# once completed siblings reach the cap, exit 3) and this driver's own checkpoint
# every CHECKPOINT_EVERY runs.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT" || exit 2

PY="$REPO_ROOT/.venv/bin/python"; [ -x "$PY" ] || PY="python3"

MANIFEST="manifest/delivery-manifest.yaml"
PHASE="screening-batch1"
OUT_ROOT="results"
BATCH_DIR="$OUT_ROOT/$PHASE"
SPEND_CAP_USD=75
REPS=3
CHECKPOINT_EVERY=10
CACHE_STATE="cold"
ISOLATION="container"
EGRESS="allowlist"
PROJECT="vital-octagon-19612"
QUIET_LOOKBACK_MIN=15        # background-traffic window checked before the batch
DRY_RUN=0
WITH_P2=0                    # the two OPTIONAL P2 cells (F1, F3); off => 126 runs
START_AT=1                   # 1-based index into the plan; for resuming a halted batch
KILL_SWITCH="$BATCH_DIR/HALT"

usage() {
  cat <<'USAGE'
usage: screening-batch1-driver.sh [options]
  --dry-run            exercise the full plan and every preflight, bill nothing
  --with-p2            include the two optional P2 cells (F1, F3) -> 132 runs
  --reps N             repetitions per cell (registered: 3)
  --spend-cap-usd N    in-runner kill-switch (registered: 75)
  --start-at N         resume a halted batch at plan index N (1-based)
  --list               print the run plan and exit
  --manifest PATH      DRY-RUN ONLY: substitute a manifest, so the preflights past
                       the sealed-artifact gate can be exercised before the real
                       artifacts are frozen. Refused without --dry-run — it would
                       otherwise be a way to run the batch around that gate.
  -h, --help           this
USAGE
}

LIST_ONLY=0
MANIFEST_OVERRIDDEN=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --with-p2) WITH_P2=1 ;;
    --reps) REPS="$2"; shift ;;
    --spend-cap-usd) SPEND_CAP_USD="$2"; shift ;;
    --start-at) START_AT="$2"; shift ;;
    --list) LIST_ONLY=1 ;;
    --manifest) MANIFEST="$2"; MANIFEST_OVERRIDDEN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "driver: unknown argument '$1'" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

log()  { printf '%s  %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
fail() { printf '%s  REFUSING: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2; exit 2; }

# --------------------------------------------------------------------------- #
# The registered arm map (cp-screen-prereg.md §4)
#
# P3 is a routing POLICY, not a CLI id: the C5/P3 arm is launched as --config C5
# and the runner hash-verifies routing_policies.P3 from the manifest.
# --------------------------------------------------------------------------- #
SOLO_ARMS="P0 C2 C3 C3-med C3-prev"      # every task
NO_C5_TASK="tasks/suite/W6-pr-review"    # review task: no executor deliverable to delegate
P1_TASK="tasks/suite/W3-migration"       # the registered escalation probe, this task only
P2_TASKS="tasks/pilot-realworld tasks/suite/W1-test-generation"   # frozen splits only

ROSTER="
tasks/pilot-realworld
tasks/suite/W4-complex-bugfix
tasks/suite/W1-test-generation
tasks/suite/W4b-zarr-consolidated-order
tasks/suite/W3-migration
tasks/suite/W1b-zarr-block-mask-properties
tasks/suite/W6-pr-review
"

contains_word() {  # contains_word <needle> "<space-separated haystack>"
  case " $2 " in *" $1 "*) return 0 ;; esac
  return 1
}

arms_for_task() {  # echo the arm list registered for one task dir
  local task="$1" arms="$SOLO_ARMS"
  [ "$task" = "$NO_C5_TASK" ] || arms="$arms C5"
  [ "$task" = "$P1_TASK" ] && arms="$arms P1"
  if [ "$WITH_P2" -eq 1 ] && contains_word "$task" "$P2_TASKS"; then arms="$arms P2"; fi
  echo "$arms"
}

build_plan() {  # one "<task> <arm> <rep>" per line, in execution order
  local task arm rep
  for task in $ROSTER; do
    for arm in $(arms_for_task "$task"); do
      for rep in $(seq 1 "$REPS"); do
        echo "$task $arm $rep"
      done
    done
  done
}

PLAN="$(build_plan)"
TOTAL="$(printf '%s\n' "$PLAN" | grep -c .)"

if [ "$LIST_ONLY" -eq 1 ]; then
  printf '%s\n' "$PLAN" | nl -ba
  echo "total runs: $TOTAL (reps=$REPS, with_p2=$WITH_P2)"
  exit 0
fi

# --------------------------------------------------------------------------- #
# Preflight — every check is a REFUSAL, not a warning. Nothing is created and
# nothing is billed until all of them pass.
# --------------------------------------------------------------------------- #
log "=== preflight ==="

# 0. The manifest override is a testing affordance, never a live path: a live
#    batch always reads the pinned manifest, whatever was passed.
if [ "$MANIFEST_OVERRIDDEN" -eq 1 ] && [ "$DRY_RUN" -eq 0 ]; then
  fail "--manifest is dry-run only; a live batch reads the pinned manifest/delivery-manifest.yaml"
fi
[ -f "$MANIFEST" ] || fail "manifest not found: $MANIFEST"
[ "$MANIFEST_OVERRIDDEN" -eq 1 ] && log "warn manifest OVERRIDDEN for this dry run: $MANIFEST"

# 1. Registered run count. The driver and the package must agree on the number
#    before a single run exists, or the batch cannot be checked against it later.
EXPECTED=126; [ "$WITH_P2" -eq 1 ] && EXPECTED=132
if [ "$REPS" -eq 3 ] && [ "$TOTAL" -ne "$EXPECTED" ]; then
  fail "plan is $TOTAL runs, registered count is $EXPECTED — arm map has drifted from cp-screen-prereg.md §4"
fi
log "ok   plan: $TOTAL runs (reps=$REPS, optional P2 $([ "$WITH_P2" -eq 1 ] && echo included || echo excluded))"

# 2. Spend authorization. Live mode needs the approved CP-SPEND to have been
#    turned into an env grant by a human; --dry-run needs nothing.
if [ "$DRY_RUN" -eq 0 ] && [ "${LAB_ALLOW_SPEND:-}" != "1" ]; then
  fail "live batch without LAB_ALLOW_SPEND=1 (CLAUDE.md rule 5: needs CHECKPOINT APPROVED: CP-SPEND)"
fi
log "ok   spend authorization ($([ "$DRY_RUN" -eq 1 ] && echo 'dry-run, nothing bills' || echo 'LAB_ALLOW_SPEND=1'))"

# 3. Sealed artifacts. A task whose hidden test or defect map is not frozen has no
#    gradable outcome: running it would burn budget to produce an ungradable diff.
#    `awaiting_human` in the manifest IS the PENDING-FREEZE state.
PENDING="$("$PY" - "$MANIFEST" <<'PYEOF'
import sys, yaml
keys = {"pilot_task": "F1 pilot", "w4_task": "F2 W4", "w1_task": "F3 W1",
        "w4b_task": "W4b-zarr", "w3_task": "W3-migration",
        "w1b_task": "W1b-zarr", "w6_task": "W6-pr-review"}
m = yaml.safe_load(open(sys.argv[1], encoding="utf-8")) or {}
for key, label in keys.items():
    entry = m.get(key) or {}
    sealed = entry.get("sealed_hidden_test") or entry.get("sealed_defect_map")
    if sealed is None:
        print(f"{label}: no sealed artifact declared in manifest key '{key}'")
    elif sealed.get("status") == "awaiting_human" or not sealed.get("sha256"):
        print(f"{label}: PENDING-FREEZE (manifest '{key}' has no frozen version+sha256)")
PYEOF
)" || fail "could not read sealed-artifact status from $MANIFEST"
if [ -n "$PENDING" ]; then
  printf '%s\n' "$PENDING" | sed 's/^/       /' >&2
  fail "sealed artifacts are not frozen — CP-SCREEN-PREREG is not approvable, so the batch cannot start"
fi
log "ok   all 7 sealed artifacts frozen (version + sha256 in the manifest)"

# 4. Task identity + declared arms. task_id is the first field of every run
#    directory name, so a manifest/task.yaml disagreement silently splits a task's
#    results across two keys; and a run under an arm the task never declared is a
#    run outside the registered matrix.
for task in $ROSTER; do
  [ -f "$task/task.yaml" ] || fail "$task/task.yaml missing"
  MISMATCH="$("$PY" - "$MANIFEST" "$task" "$(arms_for_task "$task")" <<'PYEOF'
import sys, yaml
manifest_path, task_dir, arms = sys.argv[1], sys.argv[2], sys.argv[3].split()
m = yaml.safe_load(open(manifest_path, encoding="utf-8")) or {}
t = yaml.safe_load(open(f"{task_dir}/task.yaml", encoding="utf-8")) or {}
entry = m.get(t.get("manifest_key"), {}) or {}
if entry.get("task_id") != t.get("task_id"):
    print(f"task_id disagrees: manifest={entry.get('task_id')!r} task.yaml={t.get('task_id')!r}")
declared = set(t.get("configurations") or [])
missing = sorted(set(arms) - declared)
if missing:
    print(f"declares {sorted(declared)} but the registered matrix needs {missing}")
PYEOF
)" || fail "could not read $task/task.yaml"
  [ -z "$MISMATCH" ] || { printf '       %s: %s\n' "$task" "$MISMATCH" >&2
    fail "task declarations diverge from the registered matrix (cp-screen-prereg.md §7.1/§7.2)"; }
done
log "ok   7 tasks: task_id matches the manifest, declared arms cover the registered matrix"

# 5. Product-B pin. run.py re-checks this per run; checking once here fails the
#    batch in the first second rather than after the first billed run.
AGY_PIN="$("$PY" -c "import yaml,sys;print((yaml.safe_load(open(sys.argv[1],encoding='utf-8'))or{})['subject_isolation']['agent_leg']['agy_version'])" "$MANIFEST")" \
  || fail "no subject_isolation.agent_leg.agy_version pin in $MANIFEST"
AGY_SEEN="$(agy --version 2>/dev/null | tr -d '[:space:]')" || AGY_SEEN=""
[ -n "$AGY_SEEN" ] || fail "agy --version returned nothing — unavailable is a refusal, never a pass (CLAUDE.md rule 3)"
[ "$AGY_SEEN" = "$AGY_PIN" ] || fail "agy version $AGY_SEEN != manifest pin $AGY_PIN"
export AGY_CLI_DISABLE_AUTO_UPDATE=1
log "ok   agy $AGY_SEEN == pin; AGY_CLI_DISABLE_AUTO_UPDATE=1 exported"

# 6. Egress allowlist integrity. The policy name + hash are stamped into every
#    run's identity.network_policy, so an edited list must not be stamped as the
#    pinned one.
POLICY_FILE="$("$PY" -c "import yaml,sys;print((yaml.safe_load(open(sys.argv[1],encoding='utf-8'))or{})['subject_isolation']['agent_leg_egress']['policy_file'])" "$MANIFEST")"
POLICY_PIN="$("$PY" -c "import yaml,sys;print((yaml.safe_load(open(sys.argv[1],encoding='utf-8'))or{})['subject_isolation']['agent_leg_egress']['policy_sha256'])" "$MANIFEST")"
POLICY_SEEN="$(sha256sum "$POLICY_FILE" | cut -d' ' -f1)"
[ "$POLICY_SEEN" = "$POLICY_PIN" ] || fail "egress allowlist $POLICY_FILE hash $POLICY_SEEN != manifest pin $POLICY_PIN"
log "ok   egress allowlist matches the manifest pin"

# 7. Docker. The containerized agent leg is a SPEC §5.1 hard precondition for
#    screening; without a daemon there is no posture to stamp.
command -v docker >/dev/null 2>&1 || fail "docker not found — the containerized agent leg is a SPEC §5.1 screening precondition"
docker info >/dev/null 2>&1 || fail "docker daemon unreachable"
log "ok   docker reachable"

# 8. Quiet window. Nothing but the time window separates a subject run from a
#    background job on the same model, so background traffic on a subject model is
#    a hard stop: it would be attributed to our runs.
QUIET="$("$PY" - "$PROJECT" "$QUIET_LOOKBACK_MIN" <<'PYEOF'
import datetime, sys
from harness.collectors.vertex_token_collector import GcloudMonitoringClient, build_filter
project, minutes = sys.argv[1], int(sys.argv[2])
models = ["gemini-3.7-flash", "gemini-3.6-flash"]
now = datetime.datetime.now(datetime.timezone.utc)
start = now - datetime.timedelta(minutes=minutes)
flt = build_filter(models, ["google"])
try:
    series = GcloudMonitoringClient().list_time_series(project, flt, (start, now))
except Exception as exc:                                    # noqa: BLE001
    print(f"UNKNOWN {exc}")                                 # unknown is NOT quiet
    raise SystemExit(0)
total = sum(int(p["value"].get("int64Value") or p["value"].get("doubleValue") or 0)
            for ts in series for p in ts.get("points", []))
print(f"{'QUIET' if total == 0 else 'NOISY'} {total} tokens in the last {minutes}m")
print(f"FILTER {flt}")
PYEOF
)" || QUIET="UNKNOWN collector query failed"
printf '%s\n' "$QUIET" | sed 's/^/       /'
case "$QUIET" in
  QUIET*) log "ok   quiet window: no background traffic on the subject models" ;;
  *) if [ "$DRY_RUN" -eq 1 ]; then
       log "warn quiet window not established — tolerated in --dry-run (nothing is collected)"
     else
       fail "quiet window violated or unverifiable — background tokens on a subject model would be attributed to our runs (CLAUDE.md rules 1 and 3)"
     fi ;;
esac

# 9. Kill switch. `touch results/screening-batch1/HALT` stops the batch cleanly
#    between runs, from any shell, without killing a run mid-flight.
mkdir -p "$BATCH_DIR"
rm -f "$KILL_SWITCH"
log "ok   kill switch armed: touch $KILL_SWITCH to halt between runs"

log "=== preflight passed: $TOTAL runs, cap \$$SPEND_CAP_USD, $BATCH_DIR ==="

# --------------------------------------------------------------------------- #
# Execute — serial, halt on any nonzero exit, cost checkpoint every N runs
# --------------------------------------------------------------------------- #
idx=0
completed=0
HALT_REASON=""
while read -r task arm rep; do
  [ -n "$task" ] || continue
  idx=$((idx + 1))
  [ "$idx" -ge "$START_AT" ] || continue

  if [ -f "$KILL_SWITCH" ]; then
    HALT_REASON="kill switch $KILL_SWITCH present before plan index $idx"
    break
  fi

  log "--- [$idx/$TOTAL] $task $arm rep$rep ---"
  set -- --task "$task" --config "$arm" --rep "$rep" \
         --manifest "$MANIFEST" --phase "$PHASE" --out-root "$OUT_ROOT" \
         --cache-state "$CACHE_STATE" --spend-cap-usd "$SPEND_CAP_USD" \
         --subject-isolation "$ISOLATION" --subject-egress "$EGRESS"
  [ "$DRY_RUN" -eq 1 ] && set -- "$@" --dry-run
  "$PY" -m harness.runner.run "$@"
  rc=$?

  if [ "$rc" -ne 0 ]; then
    # 3 = in-runner spend cap (an expected, orderly stop); 1 = telemetry validation
    # failed; 2 = runner error. All of them halt: a batch that keeps going past a
    # validation failure produces a dataset nobody can trust.
    case "$rc" in
      3) HALT_REASON="in-runner spend cap reached at plan index $idx ($task $arm rep$rep)" ;;
      1) HALT_REASON="telemetry validation FAILED at plan index $idx ($task $arm rep$rep)" ;;
      *) HALT_REASON="runner exited $rc at plan index $idx ($task $arm rep$rep)" ;;
    esac
    break
  fi
  completed=$((completed + 1))

  if [ $((completed % CHECKPOINT_EVERY)) -eq 0 ]; then
    log "--- cost checkpoint after $completed completed runs ---"
    "$PY" - "$BATCH_DIR" "$SPEND_CAP_USD" <<'PYEOF' | sed 's/^/       /'
import sys
from harness.runner.run import cumulative_spend_usd
batch_dir, cap = sys.argv[1], float(sys.argv[2])
total, n_runs, n_unavailable = cumulative_spend_usd(batch_dir)
print(f"known spend floor: ${total:.4f} over {n_runs} runs (cap ${cap:.2f})")
print(f"legs with unavailable cost: {n_unavailable} "
      f"-> real spend may be HIGHER; the total is a floor, never an estimate")
if n_runs:
    print(f"mean known cost per run: ${total / n_runs:.4f}")
PYEOF
  fi
done <<< "$PLAN"

log "=== execution finished: $completed/$TOTAL runs completed ==="
[ -n "$HALT_REASON" ] && log "HALTED: $HALT_REASON"

# --------------------------------------------------------------------------- #
# Backfill — Product B has no machine-readable headless usage, so its tokens only
# ever arrive from the provider's meter. Run it here, once, after the last run:
# Cloud Monitoring ingestion lags, and a window queried too early under-reports.
# --------------------------------------------------------------------------- #
if [ "$DRY_RUN" -eq 1 ]; then
  log "dry run: skipping collector backfill (no real run windows to attribute)"
  exit 0
fi
if [ "$completed" -eq 0 ]; then
  log "no runs completed: nothing to backfill"
  exit 2
fi

log "=== collector backfill ==="
log "waiting 300s for Cloud Monitoring ingestion before querying"
sleep 300

PLAN_JSON="$BATCH_DIR/collector-plan.json"
"$PY" - "$BATCH_DIR" "$PROJECT" "$PLAN_JSON" <<'PYEOF' || fail "could not build the collector plan"
import json, os, sys
batch_dir, project, out_path = sys.argv[1], sys.argv[2], sys.argv[3]

# Which legs of which arms are metered on the Google side. Declared, never
# inferred from a model name (SPEC §6.3); the product's selector label is not the
# metered model id.
GEMINI = {"C3": {"main": "gemini-3.7-flash"},
          "C3-med": {"main": "gemini-3.7-flash"},
          "C3-prev": {"main": "gemini-3.6-flash"},
          "C5": {"executor": "gemini-3.7-flash"}}

runs = []
for name in sorted(os.listdir(batch_dir)):
    run_dir = os.path.join(batch_dir, name)
    if not os.path.isfile(os.path.join(run_dir, "summary.json")):
        continue
    parts = name.split("__")
    if len(parts) < 2 or parts[1] not in GEMINI:
        continue
    runs.append({"run_dir": run_dir, "legs": dict(GEMINI[parts[1]])})

with open(out_path, "w", encoding="utf-8") as fh:
    json.dump({"project": project, "runs": runs}, fh, indent=2)
    fh.write("\n")
print(f"collector plan: {len(runs)} Gemini-bearing runs -> {out_path}", file=sys.stderr)
PYEOF

REPORT_DIR="report/$PHASE"
mkdir -p "$REPORT_DIR"
"$PY" -m harness.collectors.vertex_token_collector \
  --plan "$PLAN_JSON" --guard-seconds 60 --report "$REPORT_DIR/backfill.json"
backfill_rc=$?
[ "$backfill_rc" -eq 0 ] || log "WARNING: backfill exited $backfill_rc — inspect $REPORT_DIR/backfill.json before treating any Product-B figure as collected"

log "=== final cost accounting ==="
"$PY" - "$BATCH_DIR" "$SPEND_CAP_USD" <<'PYEOF' | sed 's/^/       /'
import sys
from harness.runner.run import cumulative_spend_usd
batch_dir, cap = sys.argv[1], float(sys.argv[2])
total, n_runs, n_unavailable = cumulative_spend_usd(batch_dir)
print(f"known spend floor: ${total:.4f} over {n_runs} runs (cap ${cap:.2f})")
print(f"legs with unavailable cost: {n_unavailable}")
PYEOF

cat <<EOF

NEXT (human):
  1. Resume the paused Gemini workloads — the quiet window is only needed through
     the final backfill, which has now run.
  2. Re-cost the backfilled Product-B legs against the pinned pricing snapshot;
     every Gemini figure carries cost_basis_qualifier: cache_blind_upper_bound.
  3. Write report/$PHASE/ with a STATUS banner and add the dataset row to
     results/README.md (CLAUDE.md rule 8). No number enters docs/site/report
     before CP-FINDINGS.
EOF

[ -n "$HALT_REASON" ] && exit 1
exit 0
