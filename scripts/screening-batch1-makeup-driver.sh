#!/usr/bin/env bash
# Makeup passes for screening batch 1. TWO PROFILES, one body:
#
#   w3 (default) — 4 arms x 2 reps = 8 runs under the 7200s W3 budget. The arm
#                  list, reps, dataset, budget and backfill rule are byte-identical
#                  to the single-profile version of this script that ran the live
#                  W3 pass; --profile w3 changes nothing about it.
#   w6           — 5 arms x 3 reps = 15 runs under the 1200s W6 budget, after the
#                  review-delivery fix (results/screening-batch1/batch1.log G).
#
#   bash scripts/screening-batch1-makeup-driver.sh --dry-run --list   # the schedule
#   bash scripts/screening-batch1-makeup-driver.sh --dry-run          # full rehearsal
#   nohup bash scripts/screening-batch1-makeup-driver.sh > makeup.log 2>&1 &
#   nohup bash scripts/screening-batch1-makeup-driver.sh --profile w6 > w6.log 2>&1 &
#
# Two profiles NEVER run at once. Both attribute Product-B tokens by run window on
# a shared provider meter, so overlapping batches would make every C3 figure in
# both of them unattributable.
#
# WHY PROFILE w3 EXISTS. Batch 1 ran every task under a flat 1800s agent timeout.
# W3 is the largest task in the suite and the designated escalation probe, and the
# bound censored it: 12 of 21 attempts were killed before the agent finished. A
# right-censored attempt is indistinguishable from a capability failure, so the
# W3-escalation registration cannot be graded against batch 1 at all — the
# decision table reports it `confounded_by_run_budget` and withholds the verdict.
# This pass re-buys the four arms that registration needs, under the 7200s budget,
# into a SEPARATE dataset.
#
#   SCOPE. Arms P0, C2, C3, P1 — the escalation probe (P1), its economical baseline
#   (C2), and the two solo references the registration reads against. Not the full
#   batch-1 W3 arm set: C3-med / C3-prev / C5 belong to the H-effort and delegation
#   panels, which are confounded on this task for the same reason but are not what
#   this pass is scoped to buy. Their batch-1 cells stay reported as confounded.
#
#   REPS. 2, not batch 1's 3. The registration is graded on two binary observations
#   (did the economical arm clear the gate; did the escalation branch fire), not on
#   a dispersion estimate. 2 reps per arm is enough to see a split; it is NOT enough
#   for a variance claim and no figure from this dataset may carry one.
#
# WHY PROFILE w6 EXISTS. Batch 1's W6 cells are not confounded, they are VOID: the
# artifact under review was never delivered to the agent, so all 15 attempts
# reviewed an empty room and produced a 0-byte diff. That is an instrument defect,
# not a result, and it is adjudicated as void in batch 1 rather than scored. The
# harness now delivers the sealed diff and names the report file the gate reads
# (results/screening-batch1/batch1.log G). This pass buys W6's full registered
# roster — 5 arms x 3 reps — under the fixed instrument.
#
#   THE FIX CHANGES THE INSTRUMENT, so this is a new dataset and never a repair of
#   batch 1's W6 cells: they stay void. A void cell and a fixed-instrument cell are
#   not two observations of the same thing.
#
#   REPS. 3 — the registered `reps_screening` for this task, unchanged from batch 1.
#   Three reps still support no dispersion claim.
#
# WHAT NEITHER PROFILE IS. Neither patches batch 1. Batch-1 cells stay exactly as
# they are, labelled confounded or void; each makeup dataset is its own directory
# with its own report (CLAUDE.md rule 8, append-only per batch). Two datasets run
# under different instrument settings are never merged into one cell — that is why
# a makeup is a new directory and not a --start-at.
#
# Runs are strictly SERIAL, for the same reason batch 1 was: Product-B effort
# levels are not label-separable in the provider's metering surface, so C3
# attribution rests on non-overlapping run windows and nothing else.
#
# Spend: live mode bills a real account and requires an approved CP-SPEND plus
# LAB_ALLOW_SPEND=1. The in-runner --spend-cap-usd kill-switch is set to 150 here
# deliberately: batch 1's corresponding arms cost well under that on either task,
# so the cap must NOT be the thing that ends a pass. A cap that binds mid-pass
# would leave the makeup half-bought and ungradable, which is worse than not
# starting it.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT" || exit 2

PY="$REPO_ROOT/.venv/bin/python"; [ -x "$PY" ] || PY="python3"

MANIFEST="manifest/delivery-manifest.yaml"
OUT_ROOT="results"
SPEND_CAP_USD=150            # deliberately non-binding; see the header
CHECKPOINT_EVERY=4
CACHE_STATE="cold"
ISOLATION="container"
EGRESS="allowlist"
PROJECT="vital-octagon-19612"
QUIET_LOOKBACK_MIN=15
QUIET_PROBE_MIN=10
QUIET_RETRIES=3
QUIET_RETRY_SLEEP=300
DRY_RUN=0
START_AT=1
PROFILE="w3"
REPS_OVERRIDE=""

usage() {
  cat <<'USAGE'
usage: screening-batch1-makeup-driver.sh [options]
  --profile w3|w6|confound
                       which makeup pass (default w3). NEVER run two at once:
                       all three attribute Product-B tokens by run window on one
                       meter, and a second driver's legs would land in the window.
  --dry-run            exercise the full plan and every preflight, bill nothing
  --reps N             repetitions per arm (default: the profile's)
  --spend-cap-usd N    in-runner kill-switch (default 150, deliberately non-binding)
  --start-at N         resume at plan index N (1-based)
  --no-resume          re-buy cells that already exist and validate
  --list               print the run plan and the schedule, then exit
  --manifest PATH      DRY-RUN ONLY: substitute a manifest
  -h, --help           this
USAGE
}

LIST_ONLY=0
MANIFEST_OVERRIDDEN=0
NO_RESUME=0
while [ $# -gt 0 ]; do
  case "$1" in
    --profile) PROFILE="$2"; shift ;;
    --dry-run) DRY_RUN=1 ;;
    --reps) REPS_OVERRIDE="$2"; shift ;;
    --spend-cap-usd) SPEND_CAP_USD="$2"; shift ;;
    --start-at) START_AT="$2"; shift ;;
    --no-resume) NO_RESUME=1 ;;
    --list) LIST_ONLY=1 ;;
    --manifest) MANIFEST="$2"; MANIFEST_OVERRIDDEN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "makeup-driver: unknown argument '$1'" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

# --------------------------------------------------------------------------- #
# Profiles. Everything below this block is shared; everything task-specific is
# here, so the two passes cannot drift apart in the parts that must not differ
# (isolation, egress, quiet-window contract, resume rule, refusal semantics).
#
# PROBE_MODELS is the roster's OWN metered models and nothing else. A model no arm
# in this pass calls cannot contaminate it, and blocking on somebody else's traffic
# on it would refuse a clean batch.
#
# The backfill rule differs on purpose. w3 stays on v2 with the fixed per-run
# ceiling because that is what its live pass ran under and a driver must not
# silently re-describe a dataset already on disk; its legs are re-attributed under
# v3 append-only by the separate backfill pass (report/screening-batch1/
# backfill-v3.json). w6 is bought fresh and so runs v3 from the start: its long
# Gemini legs are exactly the case the fixed 3M ceiling refuses for duration
# rather than contamination.
# --------------------------------------------------------------------------- #
case "$PROFILE" in
  w3)
    PHASE="screening-batch1-makeup"
    LABEL="makeup-batch"
    TASK="tasks/suite/W3-migration"
    SEALED_KEY="w3_task"
    ARMS="P0 C2 C3 P1"
    DEFAULT_REPS=2
    EXPECTED_TOTAL=8         # 4 arms x 2 reps, at the profile's default reps
    EXPECTED_TIMEOUT_S=7200  # the pin this pass exists to run under
    GEMINI_ARMS="C3"         # the only Google-metered arm in this roster
    PROBE_MODELS="gemini-3.7-flash"
    GEMINI_MAP_JSON='{"C3": {"main": "gemini-3.7-flash"}}'
    ATTRIBUTION_RULE="v2"
    TAIL_SECONDS=300
    TAIL_SILENCE_SECONDS=300
    CEILING_ARGS="--ceiling-input-tokens 3000000"
    SUPPLEMENTS="results/screening-batch1 (W3 cells, confounded by the flat 1800s agent timeout)"
    WHY="Batch 1 ran W3 under a flat 1800s agent budget and 12 of 21 attempts were killed before the agent finished, so the W3-escalation registration is not gradable against that dataset. This pass re-buys the four arms the registration reads, under the per-task budget pinned in tasks/suite/W3-migration/task.yaml."
    NOT_A_REPLACEMENT="Batch-1 W3 cells are not superseded or edited. They remain in results/screening-batch1 labelled confounded_by_run_budget. Cells run under different instrument settings are never merged."
    REPS_CAVEAT="2 reps per arm supports the registration's two binary observations. It does not support a dispersion or variance claim and no figure from this dataset may carry one."
    NEXT_GRADE="Grade the W3-escalation registration against THIS dataset. Batch 1 stays confounded_by_run_budget; it is not re-graded and not merged in."
    ;;
  w6)
    PHASE="screening-batch1-makeup-w6"
    LABEL="makeup-batch-w6"
    TASK="tasks/suite/W6-pr-review"
    SEALED_KEY="w6_task"
    ARMS="P0 C2 C3 C3-med C3-prev"
    DEFAULT_REPS=3
    EXPECTED_TOTAL=15        # 5 arms x 3 reps, the registered W6 roster
    EXPECTED_TIMEOUT_S=1200
    GEMINI_ARMS="C3 C3-med C3-prev"
    PROBE_MODELS="gemini-3.7-flash gemini-3.6-flash"
    GEMINI_MAP_JSON='{"C3": {"main": "gemini-3.7-flash"}, "C3-med": {"main": "gemini-3.7-flash"}, "C3-prev": {"main": "gemini-3.6-flash"}}'
    ATTRIBUTION_RULE="v3"
    TAIL_SECONDS=900
    TAIL_SILENCE_SECONDS=300
    CEILING_ARGS="--ceiling-input-tokens-per-second 25000"
    SUPPLEMENTS="results/screening-batch1 (W6 cells, VOID — the artifact under review was never delivered to the agent)"
    WHY="Batch 1's 15 W6 cells are void: nothing in the harness read task.yaml's review_diff, so every agent got a bare checkout with no diff to review and no named file to write findings to, and all 15 produced a 0-byte agent-solution.diff. The delivery defect and the two found with it are fixed in the harness (results/screening-batch1/batch1.log G). This pass buys the registered W6 roster under the fixed instrument."
    NOT_A_REPLACEMENT="Batch-1 W6 cells are not superseded or repaired. They remain in results/screening-batch1 adjudicated void. The fix changes the instrument, so a void cell and a cell from this dataset are not two observations of the same thing and are never merged."
    REPS_CAVEAT="3 reps per arm is the registered reps_screening for this task. It does not support a dispersion or variance claim and no figure from this dataset may carry one."
    NEXT_GRADE="Report W6 from THIS dataset only. Batch 1's W6 cells stay void; they are not re-graded, not back-filled and not merged in."
    ;;
  confound)
    PHASE="screening-batch1-confound-makeup"
    LABEL="makeup-batch-confound"
    TASK=""                  # per CELL, not per profile — the plan carries the task
    SEALED_KEY=""            # per task, read from each task.yaml's manifest_key
    ARMS="P0 C2 P1 C5"
    DEFAULT_REPS=0           # reps are per cell; the plan is an explicit list
    EXPECTED_TOTAL=11
    EXPECTED_TIMEOUT_S=""    # per task; checked task-by-task instead
    GEMINI_ARMS="C5"         # the only Google-metered arm in this roster
    PROBE_MODELS="gemini-3.7-flash"
    GEMINI_MAP_JSON='{"C5": {"executor": "gemini-3.7-flash"}}'
    ATTRIBUTION_RULE="v3"
    TAIL_SECONDS=900
    TAIL_SILENCE_SECONDS=300
    CEILING_ARGS="--ceiling-input-tokens-per-second 25000"
    SUPPLEMENTS="results/screening-batch1 and results/screening-batch1-makeup (the truncated cells enumerated in report/findings/confound-makeup-enumeration.log)"
    WHY="Batch 1 ran every task under a flat 1800s agent budget. A run the harness killed at the bound is right-censored: it is indistinguishable from a capability failure, so it is not evidence about the model either way. This pass re-buys the censored cells that no existing makeup dataset already covers, each under its OWN task's pinned budget."
    NOT_A_REPLACEMENT="No earlier cell is superseded or edited. The truncated originals stay where they are, labelled truncated. A cell run under an 1800s bound and a cell run under its task's own budget are not two observations of the same thing and are never merged."
    REPS_CAVEAT="This dataset is a list of individual replacement slots, not a rep panel: a cell here may be rep 1 or rep 3 of its arm depending on which rep was censored. Nothing in it supports a dispersion or variance claim."
    NEXT_GRADE="Read each cell alongside the surviving reps of the same arm in its ORIGINAL dataset, never pooled with the truncated attempt it replaces. Two W3 slots (P0 rep1, P1 rep1) are deliberately absent — see the limitation ledger. The W6 C2 rep2 slot lives here rather than with the rest of the W6 roster; the consolidated table records its provenance."
    # The 16 runs enumerated in report/findings/confound-makeup-enumeration.log,
    # collapsed to one slot per (task, config, rep) and minus the two slots that
    # are a budget-exhaustion FINDING rather than a hole: W3 P0 rep1 and W3 P1
    # rep1 were truncated at 1800s in batch 1 and then timed out AGAIN at their
    # task's own 7200s budget in the W3 makeup — "does not complete at 2h" is the
    # result, not a gap to buy. 16 runs - 5 duplicate (task,config,rep) rows
    # - 2 exhausted slots = 11.
    #
    # W6 C2 rep2 is in this list, not resumed into results/screening-batch1-makeup-w6:
    # that dataset already holds a run for the cell (a 1200s claude_timeout), so
    # the w6 resume index counts it settled and would skip it. Its batch-1 attempt
    # is void on the delivery defect, so this is only its SECOND attempt at the
    # correct budget, not a third — it is a hole, not yet an exhaustion finding.
    CELLS="
tasks/suite/W1-test-generation C5 1
tasks/suite/W1b-zarr-block-mask-properties P0 1
tasks/suite/W3-migration P0 3
tasks/suite/W3-migration C2 3
tasks/suite/W3-migration P1 3
tasks/suite/W3-migration C5 1
tasks/suite/W3-migration C5 2
tasks/suite/W3-migration C5 3
tasks/suite/W4b-zarr-consolidated-order C5 1
tasks/suite/W4b-zarr-consolidated-order C5 2
tasks/suite/W6-pr-review C2 2
"
    ;;
  *)
    echo "makeup-driver: unknown --profile '$PROFILE' (expected w3, w6 or confound)" >&2
    usage >&2; exit 2 ;;
esac
CELLS="${CELLS:-}"

REPS="${REPS_OVERRIDE:-$DEFAULT_REPS}"
BATCH_DIR="$OUT_ROOT/$PHASE"
KILL_SWITCH="$BATCH_DIR/HALT"
DEFERRED_LOG="$BATCH_DIR/deferred-contaminated.tsv"

log()  { printf '%s  %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
fail() { printf '%s  REFUSING: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2; exit 2; }

# A dry run drives STUB adapters. Its output must never land under results/ — see
# the batch-1 driver's note; same rule, same reason (CLAUDE.md rules 1 and 8).
if [ "$DRY_RUN" -eq 1 ]; then
  OUT_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/lab-dryrun-makeup.XXXXXXXX")"
  BATCH_DIR="$OUT_ROOT/$PHASE"
  KILL_SWITCH="$BATCH_DIR/HALT"
  DEFERRED_LOG="$BATCH_DIR/deferred-contaminated.tsv"
fi

# --------------------------------------------------------------------------- #
# Quiet-window probe — identical contract to the batch-1 driver. Time is the only
# thing separating a subject run's tokens from anyone else's on the same publisher
# model. UNKNOWN is never treated as quiet.
# --------------------------------------------------------------------------- #
quiet_probe() {  # quiet_probe <lookback-minutes>
  "$PY" - "$PROJECT" "$1" "$PROBE_MODELS" <<'PYEOF' 2>/dev/null || echo "UNKNOWN collector query failed"
import datetime, sys
from harness.collectors.vertex_token_collector import GcloudMonitoringClient, build_filter
project, minutes = sys.argv[1], int(sys.argv[2])
# Only the models THIS roster actually meters (the profile's PROBE_MODELS). The w3
# pass has no 3.6 arm, so 3.6 traffic is somebody else's business and must not
# block a batch it cannot contaminate; the w6 pass has a C3-prev arm and does
# probe it.
models = sys.argv[3].split()
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
}

build_plan() {  # one "<task-dir> <arm> <rep>" per line, in execution order
  local arm rep
  # An explicit cell list is a plan in its own right: the confound pass replaces
  # named censored slots, so its scope is a list of cells and not a matrix, and
  # writing it as arms x reps would claim a rep panel this dataset does not buy.
  if [ -n "$CELLS" ]; then
    printf '%s\n' "$CELLS" | grep .
    return 0
  fi
  for arm in $ARMS; do
    for rep in $(seq 1 "$REPS"); do
      echo "$TASK $arm $rep"
    done
  done
}

PLAN="$(build_plan)"
TOTAL="$(printf '%s\n' "$PLAN" | grep -c .)"
PLAN_TASKS="$(printf '%s\n' "$PLAN" | awk 'NF {print $1}' | sort -u)"

task_id_of() {  # task_id_of <task-dir>
  "$PY" -c \
    "import sys,yaml;print((yaml.safe_load(open(sys.argv[1]+'/task.yaml',encoding='utf-8')) or {})['task_id'])" \
    "$1" 2>/dev/null
}

for t in $PLAN_TASKS; do
  [ -n "$(task_id_of "$t")" ] || fail "no task_id in $t/task.yaml"
done
# Single-task profiles keep the scalar they have always had; the multi-task
# profile has no such thing, and a stale scalar in its log would name the wrong
# task on every line.
TASK_ID="$([ -n "$TASK" ] && task_id_of "$TASK" || echo "(per cell)")"

# --------------------------------------------------------------------------- #
# Resume index. Same contract as batch 1: a cell is settled only if its run dir
# exists AND its telemetry passes audit-grade validation. Resume matters more here
# than it did there — a single W3 attempt may now run for two hours, and the idle
# reaper on this host can stop a long-lived shell.
# --------------------------------------------------------------------------- #
RESUME=$((1 - NO_RESUME))
RESUME_DIR="results/$PHASE"
SETTLED=""
RESUME_REPORT=""

scan_completed() {
  [ -d "$RESUME_DIR" ] || return 0
  "$PY" - "$RESUME_DIR" <<'PYEOF'
import os
import sys

from harness.telemetry.telemetry import validate

batch_dir = sys.argv[1]
for name in sorted(os.listdir(batch_dir)):
    run_dir = os.path.join(batch_dir, name)
    if not os.path.isdir(run_dir):
        continue
    parts = name.split("__")
    if len(parts) < 4 or not parts[2].startswith("rep"):
        continue
    task_id, arm, rep = parts[0], parts[1], parts[2][len("rep"):]
    if not os.path.exists(os.path.join(run_dir, "summary.json")):
        print(f"BAD|{task_id}|{arm}|{rep}|{name}: no summary.json (empty or aborted run dir)")
        continue
    try:
        ok, reasons = validate(run_dir)
    except Exception as exc:                                    # noqa: BLE001
        ok, reasons = False, [f"validate raised {exc!r}"]
    if ok:
        print(f"OK|{task_id}|{arm}|{rep}|{name}")
    else:
        first = (reasons or ["unknown"])[0]
        print(f"BAD|{task_id}|{arm}|{rep}|{name}: {first}")
PYEOF
}

build_resume_index() {
  SETTLED=""
  local n_ok=0 n_bad=0 line kind rest
  if [ "$RESUME" -eq 0 ]; then
    RESUME_REPORT="resume DISABLED (--no-resume): every plan cell will be re-run"
    return 0
  fi
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    kind="${line%%|*}"; rest="${line#*|}"
    case "$kind" in
      OK)  n_ok=$((n_ok + 1)); SETTLED="${SETTLED}${rest%%:*}|completed+validated
" ;;
      BAD) n_bad=$((n_bad + 1)); log "warn unvalidated run dir will be RE-RUN: ${rest#*|*|*|}" ;;
    esac
  done <<< "$(scan_completed)"
  RESUME_REPORT="$n_ok completed+validated$([ "$n_bad" -gt 0 ] && echo ", $n_bad unvalidated dir(s) to re-run")"
}

settled_why() {  # settled_why <task-dir> <arm> <rep>
  local key
  key="$(task_id_of "$1")|$2|$3|"
  printf '%s' "$SETTLED" |
    awk -v k="$key" 'index($0, k) == 1 { print substr($0, length(k) + 1); exit }'
}

# --------------------------------------------------------------------------- #
# The pinned agent budget. This is the ONE thing that makes this pass different
# from the batch-1 W3 cells, so it is checked before anything else can happen: a
# makeup run under the old bound would reproduce the confound it exists to remove.
# --------------------------------------------------------------------------- #
read_timeout() {  # read_timeout <task-dir> -> "<task.yaml value> <manifest value>"
  "$PY" - "$1" "$MANIFEST" <<'PYEOF'
import sys, yaml
task = yaml.safe_load(open(f"{sys.argv[1]}/task.yaml", encoding="utf-8")) or {}
manifest = yaml.safe_load(open(sys.argv[2], encoding="utf-8")) or {}
entry = manifest.get(task.get("manifest_key")) or {}
print(task.get("agent_timeout_s"), entry.get("agent_timeout_s"))
PYEOF
}

if [ "$LIST_ONLY" -eq 1 ]; then
  build_resume_index
  echo "makeup batch: $LABEL   (profile $PROFILE)"
  if [ -n "$TASK" ]; then
    echo "  task     : $TASK ($TASK_ID)"
    echo "  arms     : $ARMS   reps: $REPS   runs: $TOTAL"
  else
    echo "  tasks    : $(printf '%s\n' "$PLAN_TASKS" | tr '\n' ' ')"
    echo "  cells    : $TOTAL named replacement slots (not a rep panel)"
  fi
  echo "  dataset  : results/$PHASE/   (no earlier dataset is modified)"
  for t in $PLAN_TASKS; do
    read -r T_TASK T_MANIFEST <<< "$(read_timeout "$t")"
    echo "  budget   : $(task_id_of "$t") agent_timeout_s=$T_TASK (task.yaml) / $T_MANIFEST (manifest)"
  done
  echo "  spend cap: \$$SPEND_CAP_USD in-runner kill-switch"
  echo "  resume   : $RESUME_REPORT"
  echo
  # The budget is per AGENT LEG, so P1 (economical attempt, then the strong one
  # if it escalates) and C5 (planner, then executor) can spend it twice in one
  # run. Worst case counts legs, and with per-task budgets it must count seconds
  # per cell rather than multiplying one budget by a plan size.
  WORST_S=0
  printf '%s\n' "$PLAN" | nl -ba | while read -r n task arm rep; do
    [ -n "$task" ] || continue
    tid="$(task_id_of "$task")"
    why="$(settled_why "$task" "$arm" "$rep")"
    if [ -n "$why" ]; then printf '%6s  SKIP    %s %s rep%s  (%s)\n' "$n" "$tid" "$arm" "$rep" "$why"
    else                   printf '%6s  PENDING %s %s rep%s\n' "$n" "$tid" "$arm" "$rep"; fi
  done
  for line in $(printf '%s\n' "$PLAN" | awk 'NF {print $1 "," $2}'); do
    t="${line%%,*}"; a="${line##*,}"
    read -r T_TASK _ <<< "$(read_timeout "$t")"
    case "$a" in P1|C5) legs=2 ;; *) legs=1 ;; esac
    WORST_S=$(( WORST_S + legs * T_TASK ))
  done
  echo
  echo "worst-case wall clock: $(( WORST_S / 3600 ))h of agent time across $TOTAL runs, if"
  echo "  every leg runs to its task's bound — plus gates, per-run quiet probes on the"
  echo "  $GEMINI_ARMS arm(s), and a 300s ingestion wait before backfill. Earlier legs ran"
  echo "  well under the bound, so the realistic figure is lower; the bound is what to plan for."
  echo "  The batch is resumable between runs: re-invoke to continue, or --start-at N."
  exit 0
fi

# --------------------------------------------------------------------------- #
# Preflight — every check is a REFUSAL, not a warning.
# --------------------------------------------------------------------------- #
log "=== preflight ($LABEL) ==="

if [ "$MANIFEST_OVERRIDDEN" -eq 1 ] && [ "$DRY_RUN" -eq 0 ]; then
  fail "--manifest is dry-run only; a live batch reads the pinned manifest/delivery-manifest.yaml"
fi
[ -f "$MANIFEST" ] || fail "manifest not found: $MANIFEST"
[ "$MANIFEST_OVERRIDDEN" -eq 1 ] && log "warn manifest OVERRIDDEN for this dry run: $MANIFEST"

# 1. Plan size.
if [ "$REPS" -eq "$DEFAULT_REPS" ] && [ "$TOTAL" -ne "$EXPECTED_TOTAL" ]; then
  fail "plan is $TOTAL runs, the $PROFILE makeup scope is $EXPECTED_TOTAL — the cell list has drifted"
fi
if [ -n "$CELLS" ]; then
  log "ok   plan: $TOTAL named cells across $(printf '%s\n' "$PLAN_TASKS" | grep -c .) tasks"
else
  log "ok   plan: $TOTAL runs ($ARMS x $REPS reps)"
fi

# 2. The pinned agent budget — the reason this pass exists. A multi-task plan has
#    one budget per task, so the bound is checked task by task; the single-task
#    profiles additionally pin the exact value the makeup is defined at.
T_TASK=""
for t in $PLAN_TASKS; do
  read -r t_task t_manifest <<< "$(read_timeout "$t")"
  tid="$(task_id_of "$t")"
  [ -n "$t_task" ] || fail "$tid: no agent_timeout_s in $t/task.yaml"
  if [ -n "$EXPECTED_TIMEOUT_S" ] && [ "$t_task" != "$EXPECTED_TIMEOUT_S" ]; then
    fail "$tid: task.yaml pins agent_timeout_s=$t_task, this makeup is defined at ${EXPECTED_TIMEOUT_S}s — running it under a different bound reproduces the confound it exists to remove"
  fi
  [ "$t_task" = "$t_manifest" ] || \
    fail "$tid: agent_timeout_s disagrees: task.yaml=$t_task manifest=$t_manifest (run.py would refuse each run anyway)"
  log "ok   agent budget: $tid ${t_task}s, pinned identically in task.yaml and the manifest"
  T_TASK="$t_task"   # single-task profiles read this below; multi-task uses per-cell lookups
done

# 3. Spend authorization.
if [ "$DRY_RUN" -eq 0 ] && [ "${LAB_ALLOW_SPEND:-}" != "1" ]; then
  fail "live makeup batch without LAB_ALLOW_SPEND=1 (CLAUDE.md rule 5: needs CHECKPOINT APPROVED: CP-SPEND)"
fi
log "ok   spend authorization ($([ "$DRY_RUN" -eq 1 ] && echo 'dry-run, nothing bills' || echo 'LAB_ALLOW_SPEND=1'))"

# 4 / 4b / 5 run once per task in the plan. A single-task profile loops once; the
# confound profile spans five tasks and every one of them has to clear the same
# bar before any of them is bought.
for t in $PLAN_TASKS; do
  tid="$(task_id_of "$t")"
  # Arms are per cell, so each task is checked against the arms IT is asked for.
  t_arms="$(printf '%s\n' "$PLAN" | awk -v t="$t" '$1 == t {print $2}' | sort -u | tr '\n' ' ')"

  # 4. Sealed artifact for this task, frozen. The manifest key comes from the
  #    task itself; a profile that declares one is cross-checked against it.
  PENDING="$("$PY" - "$MANIFEST" "$t" "$SEALED_KEY" <<'PYEOF'
import sys, yaml
m = yaml.safe_load(open(sys.argv[1], encoding="utf-8")) or {}
t = yaml.safe_load(open(f"{sys.argv[2]}/task.yaml", encoding="utf-8")) or {}
key, declared, label = t.get("manifest_key"), sys.argv[3], t.get("task_id")
if declared and declared != key:
    print(f"{label}: profile declares manifest key {declared!r}, task.yaml says {key!r}")
entry = m.get(key) or {}
sealed = entry.get("sealed_hidden_test") or entry.get("sealed_defect_map")
if sealed is None:
    print(f"{label}: no sealed artifact declared in manifest key {key!r}")
elif sealed.get("status") == "awaiting_human" or not sealed.get("sha256"):
    print(f"{label}: PENDING-FREEZE (no frozen version+sha256)")
PYEOF
)" || fail "could not read sealed-artifact status for $tid from $MANIFEST"
  [ -z "$PENDING" ] || { printf '%s\n' "$PENDING" | sed 's/^/       /' >&2
    fail "the $tid sealed artifact is not frozen — the makeup would produce ungradable runs"; }
  log "ok   $tid sealed artifact frozen (version + sha256 in the manifest)"

  # 4b. Review tasks: the artifact the agent reviews is DELIVERED at run time
  #     from the sealed set, so it must be on this host before anything is
  #     bought. Asking the runner's own resolver keeps this from drifting from
  #     the delivery code. It stats the file; it never reads a byte of the set.
  REVIEW_SRC="$("$PY" - "$t" "$MANIFEST" <<'PYEOF'
import sys, yaml
from harness.runner import run as R
manifest = yaml.safe_load(open(sys.argv[2], encoding="utf-8")) or {}
task = R.load_task(sys.argv[1], manifest)
print(R.review_artifact_source(task) if R.is_review_task(task) else "")
PYEOF
)" || fail "could not resolve the review artifact path for $tid"
  if [ "$SEALED_KEY" = "w6_task" ] && [ -z "$REVIEW_SRC" ]; then
    fail "$tid is not a pr_review task but the $PROFILE profile expects one"
  fi
  if [ -n "$REVIEW_SRC" ]; then
    [ -s "$REVIEW_SRC" ] || fail "the sealed review artifact for $tid is missing or empty at $REVIEW_SRC — it is human-held (hidden/README-FOR-HUMAN.md). Without it every agent reviews nothing and the pass reproduces batch 1's void exactly."
    log "ok   $tid sealed review artifact present ($(stat -c%s "$REVIEW_SRC") bytes, contents never read here)"
  fi

  # 5. Task identity + declared arms.
  MISMATCH="$("$PY" - "$MANIFEST" "$t" "$t_arms" <<'PYEOF'
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
    print(f"declares {sorted(declared)} but this makeup needs {missing}")
PYEOF
)" || fail "could not read $t/task.yaml"
  [ -z "$MISMATCH" ] || { printf '       %s\n' "$MISMATCH" >&2
    fail "$tid declarations diverge from the makeup roster"; }
  log "ok   $tid: task_id matches the manifest, its cells ($t_arms) are registered arms"
done

# 6. Product-B pin (the C3 arm).
AGY_PIN="$("$PY" -c "import yaml,sys;print((yaml.safe_load(open(sys.argv[1],encoding='utf-8'))or{})['subject_isolation']['agent_leg']['agy_version'])" "$MANIFEST")" \
  || fail "no subject_isolation.agent_leg.agy_version pin in $MANIFEST"
AGY_SEEN="$(agy --version 2>/dev/null | tr -d '[:space:]')" || AGY_SEEN=""
[ -n "$AGY_SEEN" ] || fail "agy --version returned nothing — unavailable is a refusal, never a pass (CLAUDE.md rule 3)"
[ "$AGY_SEEN" = "$AGY_PIN" ] || fail "agy version $AGY_SEEN != manifest pin $AGY_PIN"
export AGY_CLI_DISABLE_AUTO_UPDATE=1
log "ok   agy $AGY_SEEN == pin; AGY_CLI_DISABLE_AUTO_UPDATE=1 exported"

# 7. Egress allowlist integrity.
POLICY_FILE="$("$PY" -c "import yaml,sys;print((yaml.safe_load(open(sys.argv[1],encoding='utf-8'))or{})['subject_isolation']['agent_leg_egress']['policy_file'])" "$MANIFEST")"
POLICY_PIN="$("$PY" -c "import yaml,sys;print((yaml.safe_load(open(sys.argv[1],encoding='utf-8'))or{})['subject_isolation']['agent_leg_egress']['policy_sha256'])" "$MANIFEST")"
POLICY_SEEN="$(sha256sum "$POLICY_FILE" | cut -d' ' -f1)"
[ "$POLICY_SEEN" = "$POLICY_PIN" ] || fail "egress allowlist $POLICY_FILE hash $POLICY_SEEN != manifest pin $POLICY_PIN"
log "ok   egress allowlist matches the manifest pin"

# 8. Docker.
command -v docker >/dev/null 2>&1 || fail "docker not found — the containerized agent leg is a SPEC §5.1 screening precondition"
docker info >/dev/null 2>&1 || fail "docker daemon unreachable"
log "ok   docker reachable"

# 9. Quiet window.
QUIET="$(quiet_probe "$QUIET_LOOKBACK_MIN")"
printf '%s\n' "$QUIET" | sed 's/^/       /'
case "$QUIET" in
  QUIET*) log "ok   quiet window: no background traffic on the subject models" ;;
  *) if [ "$DRY_RUN" -eq 1 ]; then
       log "warn quiet window not established — tolerated in --dry-run (nothing is collected)"
     else
       fail "quiet window violated or unverifiable — background tokens on a subject model would be attributed to our runs (CLAUDE.md rules 1 and 3)"
     fi ;;
esac

# 10. Kill switch.
mkdir -p "$BATCH_DIR"
rm -f "$KILL_SWITCH"
log "ok   kill switch armed: touch $KILL_SWITCH to halt between runs"

# 11. Dataset marker. States what this dataset is and what it does NOT replace, so
#     the directory is self-describing even before its report exists. Written by
#     json.dump rather than a heredoc: the prose fields carry quotes and em-dashes,
#     and a rep-panel batch and a named-cell batch have different shapes.
MB_PATH="$BATCH_DIR/MAKEUP-BATCH.json" MB_LABEL="$LABEL" MB_PHASE="$PHASE" \
MB_PROFILE="$PROFILE" MB_SUPPLEMENTS="$SUPPLEMENTS" MB_TASK_ID="$TASK_ID" \
MB_ARMS="$ARMS" MB_REPS="$REPS" MB_TIMEOUT="$T_TASK" MB_RULE="$ATTRIBUTION_RULE" \
MB_WHY="$WHY" MB_NOT="$NOT_A_REPLACEMENT" MB_CAVEAT="$REPS_CAVEAT" \
MB_PLAN="$PLAN" MB_CELLS="$CELLS" "$PY" - <<'PYEOF' || fail "could not write the dataset marker"
import json, os, yaml

env = os.environ
marker = {
    "label": env["MB_LABEL"],
    "dataset": f"results/{env['MB_PHASE']}",
    "replaces": None,
    "profile": env["MB_PROFILE"],
    "supplements": env["MB_SUPPLEMENTS"],
}
if env["MB_CELLS"].strip():
    # A named-cell batch: each cell is a specific hole in an earlier dataset, so
    # the roster is the list itself. Reps are per cell and do not form a panel.
    cells = []
    for line in env["MB_PLAN"].splitlines():
        parts = line.split()
        if not parts:
            continue
        task_dir, arm, rep = parts[0], parts[1], int(parts[2])
        t = yaml.safe_load(open(f"{task_dir}/task.yaml", encoding="utf-8")) or {}
        cells.append({
            "task_id": t.get("task_id"), "config": arm, "rep": rep,
            "agent_timeout_s": t.get("agent_timeout_s"),
        })
    marker["cells"] = cells
    marker["task_ids"] = sorted({c["task_id"] for c in cells})
else:
    marker["task_id"] = env["MB_TASK_ID"]
    marker["arms"] = env["MB_ARMS"].split()
    marker["reps"] = int(env["MB_REPS"])
    marker["agent_timeout_s"] = int(env["MB_TIMEOUT"])
marker.update({
    "attribution_rule": env["MB_RULE"],
    "why": env["MB_WHY"],
    "not_a_replacement": env["MB_NOT"],
    "reps_caveat": env["MB_CAVEAT"],
})
with open(env["MB_PATH"], "w", encoding="utf-8") as fh:
    json.dump(marker, fh, indent=2, ensure_ascii=False)
    fh.write("\n")
PYEOF
"$PY" -c 'import json,sys;json.load(open(sys.argv[1],encoding="utf-8"))' \
  "$BATCH_DIR/MAKEUP-BATCH.json" \
  || fail "the dataset marker is not valid JSON"
log "ok   dataset marker written: $BATCH_DIR/MAKEUP-BATCH.json"

# 12. Resume index.
log "=== resume index (source: $RESUME_DIR) ==="
build_resume_index
printf '%s\n' "$RESUME_REPORT" | sed 's/^/       /'
PENDING_CELLS="$(printf '%s\n' "$PLAN" | while read -r task arm rep; do
  [ -n "$task" ] || continue
  [ -n "$(settled_why "$task" "$arm" "$rep")" ] || echo x
done | grep -c .)"
log "ok   resume: $PENDING_CELLS of $TOTAL plan cells pending"

if [ -n "$CELLS" ]; then
  log "=== preflight passed: $PENDING_CELLS pending of $TOTAL runs, per-task budgets above, cap \$$SPEND_CAP_USD, $BATCH_DIR ==="
else
  log "=== preflight passed: $PENDING_CELLS pending of $TOTAL runs, budget ${T_TASK}s/run, cap \$$SPEND_CAP_USD, $BATCH_DIR ==="
fi

await_quiet() {  # await_quiet <label>; 0 = quiet, 1 = still not quiet after retries
  local attempt=0 out
  while :; do
    out="$(quiet_probe "$QUIET_PROBE_MIN")"
    printf '%s\n' "$out" | sed 's/^/       /'
    case "$out" in QUIET*) return 0 ;; esac
    attempt=$((attempt + 1))
    if [ "$attempt" -gt "$QUIET_RETRIES" ]; then return 1; fi
    log "quiet window not established for $1 (probe $attempt/$QUIET_RETRIES) — waiting ${QUIET_RETRY_SLEEP}s"
    sleep "$QUIET_RETRY_SLEEP"
  done
}

# --------------------------------------------------------------------------- #
# Execute — serial, halt on any nonzero exit
# --------------------------------------------------------------------------- #
idx=0
completed=0
deferred=0
skipped=0
HALT_REASON=""
while read -r task arm rep; do
  [ -n "$task" ] || continue
  idx=$((idx + 1))
  [ "$idx" -ge "$START_AT" ] || continue

  if [ -f "$KILL_SWITCH" ]; then
    HALT_REASON="kill switch $KILL_SWITCH present before plan index $idx"
    break
  fi

  tid="$(task_id_of "$task")"
  WHY="$(settled_why "$task" "$arm" "$rep")"
  if [ -n "$WHY" ]; then
    skipped=$((skipped + 1))
    log "SKIP [$idx/$TOTAL] $tid $arm rep$rep — $WHY"
    continue
  fi

  read -r T_CELL _ <<< "$(read_timeout "$task")"
  log "--- [$idx/$TOTAL] $tid $arm rep$rep (budget ${T_CELL}s) ---"

  if [ "$DRY_RUN" -eq 0 ] && case " $GEMINI_ARMS " in *" $arm "*) true ;; *) false ;; esac; then
    if ! await_quiet "$arm rep$rep"; then
      deferred=$((deferred + 1))
      printf '%s\t%s\t%s\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        "$idx" "$tid" "$arm" "rep$rep" >> "$DEFERRED_LOG"
      log "DEFERRED-CONTAMINATED [$idx/$TOTAL] $tid $arm rep$rep — background traffic on the"
      log "  subject models after $((QUIET_RETRIES + 1)) probes; arm NOT run, nothing billed."
      log "  Recorded in $DEFERRED_LOG; the batch continues. A deferred cell is a HOLE."
      continue
    fi
  fi

  # --out-root is BATCH_DIR, not OUT_ROOT: a live run ignores it and derives
  # results/<phase> itself (identical path), while a dry run uses it verbatim.
  set -- --task "$task" --config "$arm" --rep "$rep" \
         --manifest "$MANIFEST" --phase "$PHASE" --out-root "$BATCH_DIR" \
         --cache-state "$CACHE_STATE" --spend-cap-usd "$SPEND_CAP_USD" \
         --subject-isolation "$ISOLATION" --subject-egress "$EGRESS"
  [ "$DRY_RUN" -eq 1 ] && set -- "$@" --dry-run
  "$PY" -m harness.runner.run "$@"
  rc=$?

  if [ "$rc" -ne 0 ]; then
    case "$rc" in
      3) HALT_REASON="in-runner spend cap reached at plan index $idx ($tid $arm rep$rep) — the cap was set NOT to bind, so investigate before raising it" ;;
      1) HALT_REASON="telemetry validation FAILED at plan index $idx ($tid $arm rep$rep)" ;;
      *) HALT_REASON="runner exited $rc at plan index $idx ($tid $arm rep$rep)" ;;
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
PYEOF
  fi
done <<< "$PLAN"

log "=== execution finished: $completed run this pass, $skipped skipped, $deferred deferred; plan $TOTAL ==="
[ -n "$HALT_REASON" ] && log "HALTED: $HALT_REASON"

if [ "$DRY_RUN" -eq 1 ]; then
  log "dry run: skipping collector backfill (no real run windows to attribute)"
  exit 0
fi
if [ "$completed" -eq 0 ]; then
  log "no runs completed: nothing to backfill"
  exit 2
fi

# --------------------------------------------------------------------------- #
# Backfill — Product-B tokens only ever arrive from the provider meter. Both rules
# used here share serialized-run ownership: a serialized run owns the meter up to
# the next subject run's window, so its own ingestion tail counts as its own. (v1
# demanded post-run silence and refused most of batch 1 for its own tail.) v3 adds
# the rate ceiling in place of the fixed per-run one. Which rule each profile runs,
# and why they differ, is in the profile block.
# --------------------------------------------------------------------------- #
log "=== collector backfill (attribution rule $ATTRIBUTION_RULE) ==="
log "waiting 300s for Cloud Monitoring ingestion before querying"
sleep 300

PLAN_JSON="$BATCH_DIR/collector-plan.json"
"$PY" - "$BATCH_DIR" "$PROJECT" "$PLAN_JSON" "$GEMINI_MAP_JSON" <<'PYEOF' || fail "could not build the collector plan"
import json, os, sys
batch_dir, project, out_path = sys.argv[1], sys.argv[2], sys.argv[3]

# Declared by the profile, never inferred from a model name (SPEC §6.3).
GEMINI = json.loads(sys.argv[4])

# The plan carries every run in this batch that can put points on those publisher
# models — i.e. the Gemini-metered arms. The Product-A arms never call them, so
# they cannot be the third party the ownership probes look for, and leaving them
# out cannot make a window absorb someone else's tokens. What it does mean is that
# a metered run owns the meter across any Product-A run that follows it, until the
# next metered run opens; that is exactly the ownership claim, and the
# no-man's-land probe and the plausibility ceiling still police it.

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
BACKFILL_REPORT="$REPORT_DIR/backfill-$ATTRIBUTION_RULE.json"
mkdir -p "$REPORT_DIR"
# shellcheck disable=SC2086  # $CEILING_ARGS is a flag+value pair; splitting is the point
"$PY" -m harness.collectors.vertex_token_collector \
  --plan "$PLAN_JSON" --attribution-rule "$ATTRIBUTION_RULE" --guard-seconds 60 \
  --tail-seconds "$TAIL_SECONDS" --tail-silence-seconds "$TAIL_SILENCE_SECONDS" \
  $CEILING_ARGS --baseline-seconds 300 \
  --report "$BACKFILL_REPORT"
backfill_rc=$?
case "$backfill_rc" in
  0) ;;
  4) log "CONTAMINATION GUARD REFUSED at least one run — nothing was written for it."
     log "  Its Product-B usage stays 'unavailable' (never zero). Evidence per run:"
     log "  $BACKFILL_REPORT and PROVIDER-BACKFILL-REFUSED-$ATTRIBUTION_RULE.json in the run dir." ;;
  *) log "WARNING: backfill exited $backfill_rc — inspect $BACKFILL_REPORT before treating any Product-B figure as collected" ;;
esac

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
  1. Summarize the makeup dataset on its own:
       python -m harness.telemetry.summarize results/$PHASE
     It pairs with report/$PHASE/ (CLAUDE.md rule 8). Add the dataset row to
     results/README.md naming that report.
  2. $NEXT_GRADE
  3. Account for the $deferred deferred-contaminated cell(s) and for any run the
     collector refused: both are HOLES, reported as missing, never averaged over.
  4. No number from this dataset enters docs, the site, or an external-facing
     report before CP-FINDINGS.
EOF

[ -n "$HALT_REASON" ] && exit 1
exit 0
