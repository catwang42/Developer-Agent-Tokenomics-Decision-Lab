/*
 * decision-report.js — renders a screening decision-table.json.
 *
 * The page has no data of its own. It renders whatever decision-table JSON it is
 * pointed at, and nothing is baked in: no numbers, no task names, no arm list beyond
 * the fixed presentation order below. Pointing it at a real dataset is gated by
 * CP-FINDINGS; the committed default source is absent, so the shipped page renders an
 * explicit empty state rather than anything that could be mistaken for a result.
 *
 * Two layers, deliberately separated:
 *   buildViewModel(table) — pure, no DOM, no globals. Every decision about what a
 *     figure *says* (is this a number, a floor, or an honest gap?) happens here, so it
 *     is testable under bare node with no browser and no dependencies.
 *   render*(...)          — thin DOM/SVG emitters that draw the view model.
 *
 * Three rules the renderer enforces structurally, not by convention:
 *
 *   1. Unavailable is never zero and never blank. A measure with no value draws a
 *      hatched slot carrying the word "unavailable" (or "no accepted outcome" when the
 *      cell accepted nothing and the ratio is undefined rather than missing) plus the
 *      reason. There is no code path that substitutes 0 for a missing figure.
 *   2. No single leaderboard. Arms are grouped into comparison bands (SPEC §2.1) and
 *      drawn in a fixed declared order that is never sorted by value. Bars from
 *      different bands are separated by a labelled gap and are not a ranking.
 *   3. Every figure carries its n and every card carries its scope line and confidence
 *      tier. A figure with no scope line is a bug, not a tidier chart.
 *
 * No external requests, no storage, no cookies: the only fetch is a same-origin
 * relative path (see resolveSource).
 */
'use strict';

/* ------------------------------------------------------------------ constants */

/**
 * Fixed presentation order and comparison band for every registered arm, with the
 * validated palette (light/dark steps checked for CVD separation, lightness band and
 * contrast). Order is declared here once and never sorted by value — a filter that
 * drops arms must not repaint the survivors.
 *
 * Placeholder labels only (CLAUDE.md rule 7): the products and models behind these
 * arms live in manifest/delivery-manifest.yaml, never in permanent material.
 */
const ARMS = [
  { id: 'P0',      band: 'a-tier',   light: '#2a78d6', dark: '#3987e5', blurb: 'Product A, strong tier, solo' },
  { id: 'C2',      band: 'a-tier',   light: '#eb6834', dark: '#d95926', blurb: 'Product A, economical tier, solo' },
  { id: 'P1',      band: 'a-policy', light: '#4a3aa7', dark: '#9085e9', blurb: 'Product A, cheap-first with escalation' },
  { id: 'P2',      band: 'a-policy', light: '#e34948', dark: '#e66767', blurb: 'Product A, scripted delegation' },
  { id: 'C3',      band: 'b-gen',    light: '#1baf7a', dark: '#199e70', blurb: 'Product B, high effort, solo' },
  { id: 'C3-med',  band: 'b-gen',    light: '#eda100', dark: '#c98500', blurb: 'Product B, medium effort, solo' },
  { id: 'C3-prev', band: 'b-gen',    light: '#e87ba4', dark: '#d55181', blurb: 'Product B, previous generation, solo' },
  { id: 'C5',      band: 'hybrid',   light: '#008300', dark: '#008300', blurb: 'Hybrid: Product A conducts, Product B executes' },
];

/** An arm the table carries but this page does not know: neutral, never a new hue. */
const OTHER_ARM = { band: 'other', light: '#6b7280', dark: '#8b93a1', blurb: 'not in the registered screening matrix' };

/**
 * The comparison views. These are the reason there is no single leaderboard: a
 * within-product tier comparison, a product black-box comparison and a hybrid-workflow
 * comparison answer different questions and cannot share a ranking (SPEC §2.1).
 */
const BANDS = [
  { id: 'a-tier',   label: 'Product A — tier',        note: 'within one product: which tier, same harness (SPEC §2.1 view 1)' },
  { id: 'a-policy', label: 'Product A — routing policy', note: 'within one product: what the policy does — a policy figure, not a model-capability claim (SPEC §2.1b)' },
  { id: 'b-gen',    label: 'Product B — generation / effort', note: 'within one product: generation and effort level (SPEC §2.1 view 1)' },
  { id: 'hybrid',   label: 'Hybrid workflow',         note: 'two products in one workflow: a workflow figure, not a head-to-head (SPEC §2.1 view 3)' },
  { id: 'other',    label: 'Other',                   note: 'arms outside the registered screening matrix' },
];

/** Human wording for each confidence tier, shown wherever a tier is displayed. */
const TIER_BLURB = {
  authoritative: 'read from product-reported usage metadata',
  derived: 'computed by the harness from authoritative inputs',
  proxy_observed: 'observed on the provider side, attributed by run window',
  derived_floor: 'a lower bound — at least one leg of the bill is unavailable',
  unavailable: 'not exposed by the product; recorded as unavailable, never zero',
  undefined: 'the ratio has no value because nothing was accepted',
};

const MEASURE_LABEL = {
  unavailable: 'unavailable',
  undefined: 'no accepted outcome',
};

/* ------------------------------------------------------------- pure utilities */

function armMeta(id) {
  const found = ARMS.find((a) => a.id === id);
  return found || Object.assign({ id: id }, OTHER_ARM);
}

function bandMeta(id) {
  return BANDS.find((b) => b.id === id) || BANDS[BANDS.length - 1];
}

/** Sort key that keeps the declared arm order; unknown arms fall to the end, by name. */
function armOrder(id) {
  const idx = ARMS.findIndex((a) => a.id === id);
  return idx === -1 ? ARMS.length : idx;
}

function fmtUsd(value) {
  if (value === null || value === undefined || !isFinite(value)) return null;
  if (value === 0) return '$0.00';
  if (Math.abs(value) < 0.01) return '$' + value.toFixed(4);
  if (Math.abs(value) < 1) return '$' + value.toFixed(3);
  if (Math.abs(value) < 100) return '$' + value.toFixed(2);
  return '$' + Math.round(value).toLocaleString('en-US');
}

function fmtInt(value) {
  if (value === null || value === undefined || !isFinite(value)) return null;
  return Math.round(value).toLocaleString('en-US');
}

function fmtPct(value, digits) {
  if (value === null || value === undefined || !isFinite(value)) return null;
  return value.toFixed(digits === undefined ? 1 : digits) + '%';
}

/** Collapse a summarizer list-valued scope field ("one distinct value" is the norm). */
function joinScope(values) {
  if (!Array.isArray(values)) return values === null || values === undefined ? null : String(values);
  if (!values.length) return null;
  return values.join(' / ');
}

/**
 * Normalise one cost measure into something a bar can be drawn from — or explicitly
 * cannot. `value` is only ever a number when the summarizer produced one; there is no
 * default and no fallback to zero.
 */
function readMeasure(slot) {
  if (!slot) {
    return { status: 'unavailable', value: null, isFloor: false, reason: 'not present in this table' };
  }
  const status = slot.status || (slot.value === null || slot.value === undefined ? 'unavailable' : 'derived');
  const numeric = typeof slot.value === 'number' && isFinite(slot.value);
  return {
    status: status,
    value: numeric ? slot.value : null,
    isFloor: status === 'derived_floor' || slot.attempt_cost_is_floor === true,
    reason: slot.reason || null,
    nAccepted: typeof slot.n_accepted === 'number' ? slot.n_accepted : null,
    nRuns: typeof slot.n_runs === 'number' ? slot.n_runs : null,
    attemptCostSum: typeof slot.attempt_cost_sum === 'number' ? slot.attempt_cost_sum : null,
  };
}

/** The label that goes on or beside a bar. A floor reads "≥"; a gap reads in words. */
function measureLabel(measure) {
  if (measure.value === null) return MEASURE_LABEL[measure.status] || 'unavailable';
  const money = fmtUsd(measure.value);
  return measure.isFloor ? '≥ ' + money : money;
}

/** Min–max dispersion of the per-attempt cost, used for the whiskers. */
function readDispersion(slot) {
  if (!slot || typeof slot.median !== 'number') {
    return {
      available: false,
      reason: (slot && slot.reason) || 'no run in this cell reported a cost',
      n: (slot && slot.n) || 0,
      ofRuns: (slot && slot.of_runs) || 0,
      runsUnavailable: (slot && slot.runs_unavailable) || 0,
    };
  }
  return {
    available: true,
    median: slot.median,
    min: typeof slot.min === 'number' ? slot.min : slot.median,
    max: typeof slot.max === 'number' ? slot.max : slot.median,
    n: slot.n || 0,
    ofRuns: slot.of_runs || slot.n || 0,
    runsUnavailable: slot.runs_unavailable || 0,
    confidence: slot.confidence || null,
  };
}

/**
 * The confidence tier a card should display: the weakest thing it depends on. A card
 * whose cost is a floor says so, rather than inheriting the acceptance gate's
 * "authoritative".
 */
function cellTier(cell) {
  const ecst = readMeasure(cell.ecst && cell.ecst.marginal_operating_usd);
  if (ecst.status === 'unavailable' || ecst.status === 'undefined') return ecst.status;
  if (ecst.isFloor) return 'derived_floor';
  const disp = readDispersion(cell.ecst && cell.ecst.attempt_cost_usd);
  if (disp.available && disp.confidence) return disp.confidence;
  return 'derived';
}

function taskLabel(table, taskId) {
  const entry = (table.task_registry || {})[taskId];
  return (entry && entry.label) || taskId;
}

/* -------------------------------------------------------------- the view model */

/**
 * Turn a decision table into everything the page draws. Pure: same input, same output,
 * no DOM. Anything the renderer needs to decide is decided here so a test can assert it.
 */
function buildViewModel(table) {
  if (!table || typeof table !== 'object') {
    return { ok: false, reason: 'no decision table supplied' };
  }
  const cells = Array.isArray(table.cells) ? table.cells : [];
  const registry = table.task_registry || {};

  const model = {
    ok: true,
    meta: buildMeta(table, cells),
    classes: buildClassPanels(table, cells),
    heat: buildHeatMatrix(table, cells),
    effort: buildEffortPanel(table, cells),
    routing: buildRoutingPanel(table, cells),
    coverage: buildCoverage(table),
    armsPresent: [],
  };
  const seen = {};
  cells.forEach((c) => { seen[c.configuration_or_policy] = true; });
  model.armsPresent = Object.keys(seen).sort((a, b) => armOrder(a) - armOrder(b) || a.localeCompare(b));
  void registry;
  return model;
}

function buildMeta(table, cells) {
  return {
    schema: table.schema || null,
    status: table.status || 'PENDING',
    sourceDataset: table.source_dataset || null,
    manifestRef: table.manifest_ref || null,
    nRuns: typeof table.n_runs === 'number' ? table.n_runs : cells.reduce((s, c) => s + (c.n_runs || 0), 0),
    nCells: typeof table.n_cells === 'number' ? table.n_cells : cells.length,
    note: table.note || null,
    screeningNote: table.screening_note || null,
    cpFindingsGate: table.cp_findings_gate || null,
    loadedRate: typeof table.loaded_rate_usd_per_min === 'number' ? table.loaded_rate_usd_per_min : null,
    // A fixture must announce itself loudly enough that no screenshot of this page can
    // be mistaken for a measurement.
    synthetic: table.synthetic === true,
    syntheticNotice: table.synthetic_notice || table.SYNTHETIC || null,
    generator: table.generator || null,
  };
}

/**
 * One panel per task class. Within a panel, one group per task and one bar per arm,
 * arms in declared order and banded by comparison view. Classes are listed
 * alphabetically — a deliberate non-ranking, since ordering classes by any measure
 * would imply the classes compete with each other.
 */
function buildClassPanels(table, cells) {
  const byClass = {};
  cells.forEach((cell) => {
    const klass = cell.task_class || 'unclassified';
    (byClass[klass] = byClass[klass] || []).push(cell);
  });

  return Object.keys(byClass).sort().map((klass) => {
    const classCells = byClass[klass];
    const taskIds = [];
    classCells.forEach((c) => { if (taskIds.indexOf(c.task_id) === -1) taskIds.push(c.task_id); });
    taskIds.sort();

    const groups = taskIds.map((taskId) => {
      const bars = classCells
        .filter((c) => c.task_id === taskId)
        .sort((a, b) => armOrder(a.configuration_or_policy) - armOrder(b.configuration_or_policy) ||
                        String(a.configuration_or_policy).localeCompare(String(b.configuration_or_policy)))
        .map((cell) => buildBar(cell));
      return { taskId: taskId, label: taskLabel(table, taskId), bars: bars, nRuns: bars.reduce((s, b) => s + b.nRuns, 0) };
    });

    // The axis must cover both the bar (ECST) and the whisker (per-attempt spread),
    // which are different measures sharing one USD axis by design — never two axes.
    let maxValue = 0;
    groups.forEach((g) => g.bars.forEach((b) => {
      if (b.measure.value !== null) maxValue = Math.max(maxValue, b.measure.value);
      if (b.dispersion.available) maxValue = Math.max(maxValue, b.dispersion.max);
    }));

    const bandsUsed = [];
    groups.forEach((g) => g.bars.forEach((b) => {
      if (bandsUsed.indexOf(b.band) === -1) bandsUsed.push(b.band);
    }));
    bandsUsed.sort((a, b) => BANDS.findIndex((x) => x.id === a) - BANDS.findIndex((x) => x.id === b));

    const gaps = [];
    groups.forEach((g) => g.bars.forEach((b) => {
      if (b.measure.value === null) {
        gaps.push({ taskId: g.taskId, arm: b.arm, status: b.measure.status, reason: b.measure.reason });
      }
    }));

    return {
      taskClass: klass,
      tasks: taskIds.map((id) => ({ taskId: id, label: taskLabel(table, id) })),
      groups: groups,
      maxValue: maxValue,
      hasAnyValue: maxValue > 0,
      bands: bandsUsed.map(bandMeta),
      nRuns: classCells.reduce((s, c) => s + (c.n_runs || 0), 0),
      nCells: classCells.length,
      gaps: gaps,
      scopeLines: dedupe(classCells.map((c) => c.scope_line).filter(Boolean)),
    };
  });
}

function buildBar(cell) {
  const meta = armMeta(cell.configuration_or_policy);
  const measure = readMeasure(cell.ecst && cell.ecst.marginal_operating_usd);
  const dispersion = readDispersion(cell.ecst && cell.ecst.attempt_cost_usd);
  const acceptance = cell.acceptance || {};
  return {
    arm: cell.configuration_or_policy,
    band: meta.band,
    blurb: meta.blurb,
    light: meta.light,
    dark: meta.dark,
    registered: cell.registered_arm !== false,
    nRuns: cell.n_runs || 0,
    accepted: typeof acceptance.accepted === 'number' ? acceptance.accepted : null,
    acceptanceDisplay: acceptance.display || null,
    measure: measure,
    measureLabel: measureLabel(measure),
    dispersion: dispersion,
    tier: cellTier(cell),
    scopeLine: cell.scope_line || null,
    heac: readMeasure(cell.heac),
    legs: cell.legs || null,
    taskId: cell.task_id,
  };
}

/**
 * Acceptance rate for every arm × task pair. Three distinct empty states, because
 * collapsing them would hide a protocol violation: a registered arm that did not run,
 * an arm that was never registered for that task, and a cell that ran and accepted
 * nothing (which is a real 0, not a gap).
 */
function buildHeatMatrix(table, cells) {
  const coverage = (table.arm_coverage && table.arm_coverage.by_task) || {};
  const taskIds = dedupe(cells.map((c) => c.task_id).concat(Object.keys(coverage))).sort();
  const armIds = dedupe(
    cells.map((c) => c.configuration_or_policy).concat(
      Object.keys(coverage).reduce((acc, t) => acc.concat(coverage[t].registered || []), [])
    )
  ).sort((a, b) => armOrder(a) - armOrder(b) || a.localeCompare(b));

  const index = {};
  cells.forEach((c) => { index[c.task_id + '::' + c.configuration_or_policy] = c; });

  const rows = armIds.map((arm) => ({
    arm: arm,
    band: armMeta(arm).band,
    cells: taskIds.map((taskId) => {
      const cell = index[taskId + '::' + arm];
      const cov = coverage[taskId] || {};
      if (!cell) {
        const registered = (cov.registered || []).indexOf(arm) !== -1;
        const companion = (cov.companion || []).indexOf(arm) !== -1;
        return {
          taskId: taskId, arm: arm, state: registered ? 'not-run' : (companion ? 'companion-not-run' : 'not-registered'),
          rate: null,
          note: registered ? 'registered for this task but no run in this dataset'
                           : 'not registered for this task',
        };
      }
      const acc = cell.acceptance || {};
      const of = typeof acc.of === 'number' ? acc.of : cell.n_runs || 0;
      const accepted = typeof acc.accepted === 'number' ? acc.accepted : null;
      return {
        taskId: taskId, arm: arm, state: 'ran',
        rate: accepted === null || !of ? null : accepted / of,
        accepted: accepted,
        of: of,
        display: acc.display || (accepted === null ? null : accepted + '/' + of),
        tier: acc.confidence || null,
        scopeLine: cell.scope_line || null,
        note: acc.basis || null,
      };
    }),
  }));

  return {
    tasks: taskIds.map((id) => ({ taskId: id, label: taskLabel(table, id) })),
    rows: rows,
    nRuns: cells.reduce((s, c) => s + (c.n_runs || 0), 0),
    basis: (cells[0] && cells[0].acceptance && cells[0].acceptance.basis) || null,
  };
}

/**
 * The effort panel: the registered High-vs-Medium pair per task, with the registration's
 * predicted reduction band drawn behind the observed reduction so the prediction cannot
 * be quietly re-fitted after the fact.
 */
function buildEffortPanel(table, cells) {
  const grading = (table.prereg_grading || {}).h_effort;
  if (!grading) return null;
  const reg = grading.registration || {};
  const band = reg.predicted_reduction_pct || null;

  const byTask = (grading.by_task || []).map((row) => {
    const delta = row.delta || {};
    const arms = row.arms || {};
    return {
      taskId: row.task_id,
      label: taskLabel(table, row.task_id),
      taskClass: row.task_class || null,
      inScope: row.in_registered_scope !== false,
      verdict: row.verdict,
      reductionPct: typeof delta.reduction_pct === 'number' ? delta.reduction_pct : null,
      deltaBasis: delta.basis || null,
      deltaConfidence: delta.confidence || null,
      deltaReason: delta.reason || null,
      gateParity: row.gate_parity || null,
      arms: Object.keys(arms).sort((a, b) => armOrder(a) - armOrder(b)).map((armId) => ({
        arm: armId,
        color: armMeta(armId),
        ecst: typeof arms[armId].ecst_usd === 'number' ? arms[armId].ecst_usd : null,
        status: arms[armId].status || 'unavailable',
        acceptance: (arms[armId].acceptance || {}).display || null,
        scopeLine: arms[armId].scope_line || null,
      })),
    };
  });

  const reductions = byTask.map((r) => r.reductionPct).filter((v) => typeof v === 'number');
  const lo = Math.min.apply(null, [0].concat(reductions));
  const hi = Math.max.apply(null, [(band && band.high) || 50].concat(reductions));

  return {
    registration: {
      id: reg.id || 'H-effort',
      file: reg.file || null,
      registered: reg.registered || null,
      prediction: reg.prediction || null,
      scopeNote: reg.scope_note || null,
      attributionNote: reg.attribution_note || null,
      publishEitherWay: reg.publish_either_way === true,
      arms: reg.arms || [],
      band: band,
    },
    status: grading.status || 'no_data',
    nGraded: typeof grading.n_graded === 'number' ? grading.n_graded : byTask.length,
    tally: grading.verdict_tally || {},
    note: grading.note || null,
    byTask: byTask,
    domain: { lo: Math.min(lo, 0), hi: Math.max(hi * 1.1, 10) },
    // How many cells the panel could not grade at all. Reported, not hidden: a panel
    // that silently drops ungradable cells reads as fuller coverage than it has.
    nUngradable: byTask.filter((r) => r.verdict === 'not_gradable').length,
    // Cells outside the registration's declared scope are shown but never graded.
    nExploratory: byTask.filter((r) => r.verdict === 'exploratory_not_graded').length,
    cells: cells.length,
  };
}

/**
 * The routing view: what the escalation policy actually did on the probe task, and what
 * a two-leg delegation bill looks like itemised. Both are workflow figures — neither is
 * a model-capability claim.
 */
function buildRoutingPanel(table, cells) {
  const grading = (table.prereg_grading || {}).w3_escalation || null;
  const escalation = grading ? {
    registration: {
      id: (grading.registration || {}).id || 'W3-escalation-probe',
      file: (grading.registration || {}).file || null,
      registered: (grading.registration || {}).registered || null,
      prediction: (grading.registration || {}).prediction || null,
      selectionNote: (grading.registration || {}).selection_note || null,
      publishEitherWay: (grading.registration || {}).publish_either_way === true,
    },
    taskId: grading.task_id || null,
    label: grading.task_id ? taskLabel(table, grading.task_id) : null,
    taskClass: grading.task_class || null,
    probeArm: grading.probe_arm || null,
    economicalArm: grading.economical_arm || null,
    outcome: grading.outcome || 'not_yet_run',
    outcomeBasis: grading.outcome_basis || null,
    economicalGate: grading.economical_tier_gate || 'no_data',
    branch: grading.escalation_branch || 'no_data',
    nEscalated: typeof grading.n_escalated === 'number' ? grading.n_escalated : null,
    nProbeRuns: typeof grading.n_probe_runs === 'number' ? grading.n_probe_runs : null,
    economicalSolo: grading.economical_solo || null,
    probeCell: grading.probe_cell || null,
    note: grading.note || null,
    trace: (grading.trace || []).map((run, i) => ({
      index: i + 1,
      runId: run.run_id || null,
      intention: run.intention_to_route || null,
      completed: run.completed_route || null,
      fired: run.escalation_fired === true,
      escalations: run.escalations || null,
      gates: run.gate_checks || [],
      legs: legRows(run.legs || []),
    })),
  } : null;

  // Every multi-leg cell gets an itemised bill, not just the delegation arm the brief
  // names: a two-leg bill that appears anywhere must be shown leg by leg.
  const bills = cells
    .filter((c) => c.legs && c.legs.is_multi_leg && Array.isArray(c.legs.rows) && c.legs.rows.length > 1)
    .sort((a, b) => armOrder(a.configuration_or_policy) - armOrder(b.configuration_or_policy) ||
                    String(a.task_id).localeCompare(String(b.task_id)))
    .map((c) => ({
      arm: c.configuration_or_policy,
      color: armMeta(c.configuration_or_policy),
      taskId: c.task_id,
      label: taskLabel(table, c.task_id),
      taskClass: c.task_class || null,
      nRuns: c.n_runs || 0,
      acceptance: (c.acceptance || {}).display || null,
      scopeLine: c.scope_line || null,
      tier: cellTier(c),
      basis: c.legs.basis || null,
      rows: legRows(c.legs.rows),
      total: readMeasure(c.ecst && c.ecst.marginal_operating_usd),
    }));

  return { escalation: escalation, bills: bills };
}

/** Normalise the summarizer's per-leg rows for display; unpriced legs stay unpriced. */
function legRows(rows) {
  return (rows || []).map((row) => {
    const cost = readDispersion(row.marginal_operating_usd);
    const usage = row.usage_totals || {};
    return {
      legId: row.leg_id,
      role: row.role || null,
      selector: joinScope(row.model_or_selector),
      provider: joinScope(row.provider),
      costBasis: joinScope(row.cost_basis),
      nLegs: row.n_legs || 0,
      confidence: row.confidence || null,
      unavailableLegs: row.legs_cost_unavailable || 0,
      cost: cost,
      costLabel: cost.available ? fmtUsd(cost.median) : 'unavailable',
      usage: Object.keys(usage).sort().map((key) => ({
        tokenClass: key,
        value: typeof usage[key].value === 'number' ? usage[key].value : null,
        status: usage[key].status || 'unavailable',
        reason: usage[key].reason || null,
        confidence: usage[key].confidence || null,
      })),
    };
  });
}

/** Registered-versus-observed coverage. A missing cell is shown, never omitted. */
function buildCoverage(table) {
  const cov = table.arm_coverage;
  if (!cov) return null;
  const byTask = cov.by_task || {};
  return {
    source: cov.source || null,
    armKey: cov.arm_key || null,
    complete: cov.complete === true,
    tasksNotInRegistry: cov.tasks_not_in_registry || [],
    rows: Object.keys(byTask).sort().map((taskId) => {
      const entry = byTask[taskId];
      return {
        taskId: taskId,
        label: taskLabel(table, taskId),
        taskClass: entry.task_class || null,
        registered: entry.registered || [],
        observed: entry.observed || [],
        missing: entry.missing || [],
        companion: entry.companion || [],
        companionObserved: entry.companion_observed || [],
        unregistered: entry.unregistered || [],
      };
    }),
  };
}

function dedupe(list) {
  const out = [];
  list.forEach((v) => { if (out.indexOf(v) === -1) out.push(v); });
  return out;
}

/* --------------------------------------------------------------- DOM plumbing */

const SVG_NS = 'http://www.w3.org/2000/svg';

function el(tag, attrs, children) {
  const node = document.createElement(tag);
  applyAttrs(node, attrs);
  appendAll(node, children);
  return node;
}

function svg(tag, attrs, children) {
  const node = document.createElementNS(SVG_NS, tag);
  applyAttrs(node, attrs);
  appendAll(node, children);
  return node;
}

function applyAttrs(node, attrs) {
  if (!attrs) return;
  Object.keys(attrs).forEach((key) => {
    const value = attrs[key];
    if (value === null || value === undefined || value === false) return;
    if (key === 'text') { node.textContent = value; return; }
    if (key === 'class') { node.setAttribute('class', value); return; }
    node.setAttribute(key, String(value));
  });
}

function appendAll(node, children) {
  if (!children) return;
  (Array.isArray(children) ? children : [children]).forEach((child) => {
    if (child === null || child === undefined || child === false) return;
    node.appendChild(typeof child === 'string' ? document.createTextNode(child) : child);
  });
}

/** A small labelled pill. Text wears ink tokens; the dot beside it carries identity. */
function chip(label, kind, title) {
  return el('span', { class: 'dr-chip dr-chip--' + (kind || 'neutral'), title: title || null, text: label });
}

function armSwatch(arm) {
  const meta = armMeta(arm);
  return el('span', { class: 'dr-swatch', style: '--dr-arm-light:' + meta.light + ';--dr-arm-dark:' + meta.dark });
}

function tierChip(tier) {
  if (!tier) return null;
  return chip(tier.replace(/_/g, ' '), 'tier-' + tier, TIER_BLURB[tier] || null);
}

function scopeFooter(scopeLine, tier, extra) {
  return el('p', { class: 'dr-scope' }, [
    el('span', { class: 'dr-scope__label', text: 'Scope' }),
    el('span', { class: 'dr-scope__text', text: scopeLine || 'scope line unavailable for this cell' }),
    tierChip(tier),
    extra || null,
  ]);
}

function nBadge(n, unit) {
  const word = unit || 'run';
  return el('span', {
    class: 'dr-nbadge',
    title: 'every figure in this view is computed over this many ' + word + 's',
    text: 'n = ' + (n === null || n === undefined ? '—' : n) + ' ' + word + (n === 1 ? '' : 's'),
  });
}

/** Chart + its table twin. Every figure on this page ships both. */
function figure(opts) {
  const id = 'dr-fig-' + (figure._seq = (figure._seq || 0) + 1);
  const table = opts.table;
  const wrap = el('figure', { class: 'dr-figure' }, [
    el('figcaption', { class: 'dr-figure__head' }, [
      el('span', { class: 'dr-figure__title', text: opts.title }),
      nBadge(opts.n, opts.unit),
      table ? el('button', {
        class: 'dr-toggle', type: 'button', 'aria-expanded': 'false', 'aria-controls': id,
        text: 'Table view',
      }) : null,
    ]),
    opts.subtitle ? el('p', { class: 'dr-figure__sub', text: opts.subtitle }) : null,
    opts.legend || null,
    el('div', { class: 'dr-figure__plot' }, opts.plot),
    table ? el('div', { class: 'dr-tableview', id: id, hidden: 'hidden' }, table) : null,
    opts.footnote ? el('p', { class: 'dr-figure__foot', text: opts.footnote }) : null,
  ]);
  if (table) {
    const button = wrap.querySelector('.dr-toggle');
    const view = wrap.querySelector('.dr-tableview');
    button.addEventListener('click', () => {
      const open = view.hasAttribute('hidden');
      if (open) view.removeAttribute('hidden'); else view.setAttribute('hidden', 'hidden');
      button.setAttribute('aria-expanded', open ? 'true' : 'false');
      button.textContent = open ? 'Hide table' : 'Table view';
    });
  }
  return wrap;
}

function dataTable(headers, rows, caption) {
  return el('table', { class: 'dr-table' }, [
    caption ? el('caption', { text: caption }) : null,
    el('thead', {}, el('tr', {}, headers.map((h) => el('th', { scope: 'col', text: h })))),
    el('tbody', {}, rows.map((row) => el('tr', {}, row.map((cellValue, i) => {
      const isHeader = i === 0;
      const text = cellValue === null || cellValue === undefined ? 'unavailable' : String(cellValue);
      const missing = cellValue === null || cellValue === undefined;
      return el(isHeader ? 'th' : 'td', {
        scope: isHeader ? 'row' : null,
        class: missing ? 'dr-cell--unavailable' : null,
        text: text,
      });
    })))),
  ]);
}

/* ------------------------------------------------------------------- tooltips */

let tooltipNode = null;

function tooltip() {
  if (!tooltipNode) {
    tooltipNode = el('div', { class: 'dr-tooltip', role: 'tooltip', hidden: 'hidden' });
    document.body.appendChild(tooltipNode);
  }
  return tooltipNode;
}

/** Attach a hover/focus tooltip. Keyboard-reachable, so it is not a mouse-only layer. */
function attachTip(node, linesFn) {
  const show = (event) => {
    const tip = tooltip();
    tip.textContent = '';
    linesFn().forEach((line) => {
      if (!line) return;
      tip.appendChild(el('div', { class: 'dr-tooltip__line' + (line.strong ? ' is-strong' : '') }, [
        line.label ? el('span', { class: 'dr-tooltip__label', text: line.label }) : null,
        el('span', { class: 'dr-tooltip__value', text: line.value }),
      ]));
    });
    tip.removeAttribute('hidden');
    const box = (event.target.getBoundingClientRect ? event.target : node).getBoundingClientRect();
    const top = box.top + window.scrollY - tip.offsetHeight - 10;
    tip.style.top = (top < window.scrollY ? box.bottom + window.scrollY + 10 : top) + 'px';
    tip.style.left = Math.max(8, Math.min(
      box.left + window.scrollX + box.width / 2 - tip.offsetWidth / 2,
      window.innerWidth - tip.offsetWidth - 8
    )) + 'px';
  };
  const hide = () => { if (tooltipNode) tooltipNode.setAttribute('hidden', 'hidden'); };
  node.addEventListener('mouseenter', show);
  node.addEventListener('focus', show);
  node.addEventListener('mouseleave', hide);
  node.addEventListener('blur', hide);
  if (!node.hasAttribute('tabindex')) node.setAttribute('tabindex', '0');
}

/* ------------------------------------------------------------------ axis ticks */

/** Nice round tick values covering [0, max]; ~4 gridlines, never more than 6. */
function ticks(max, count) {
  if (!(max > 0)) return [0];
  const target = count || 4;
  const raw = max / target;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) || 10 * mag;
  const out = [];
  for (let v = 0; v <= max + step * 0.001; v += step) out.push(Number(v.toFixed(10)));
  if (out[out.length - 1] < max) out.push(Number((out[out.length - 1] + step).toFixed(10)));
  return out;
}

/* ------------------------------------------------- the cost-per-outcome chart */

const BAR_W = 22;        // ≤24px marks
const BAR_GAP = 2;       // 2px surface gap between adjacent bars
const BAND_GAP = 16;     // labelled gap between comparison bands
const GROUP_GAP = 40;
const PLOT_H = 230;
const M = { top: 26, right: 18, bottom: 84, left: 68 };

function costChart(panel) {
  // Lay the bars out first so the SVG width follows the data rather than the reverse.
  let x = M.left;
  const laid = [];
  panel.groups.forEach((group, gi) => {
    if (gi > 0) x += GROUP_GAP;
    const start = x;
    let prevBand = null;
    group.bars.forEach((bar) => {
      if (prevBand !== null && bar.band !== prevBand) x += BAND_GAP;
      prevBand = bar.band;
      laid.push({ bar: bar, group: group, x: x });
      x += BAR_W + BAR_GAP;
    });
    group._start = start;
    group._end = x - BAR_GAP;
  });
  const width = x + M.right;
  const height = M.top + PLOT_H + M.bottom;
  const axisMax = panel.maxValue > 0 ? panel.maxValue : 1;
  const tickValues = ticks(axisMax);
  const top = tickValues[tickValues.length - 1] || axisMax;
  const yOf = (v) => M.top + PLOT_H - (v / top) * PLOT_H;

  const root = svg('svg', {
    class: 'dr-chart', viewBox: '0 0 ' + width + ' ' + height, role: 'img',
    'aria-label': 'Cost per accepted outcome by arm for ' + panel.taskClass.replace(/_/g, ' ') +
                  ' tasks, with per-attempt cost range',
  });
  root.appendChild(svg('defs', {}, [hatchPattern('dr-hatch-gap'), hatchPattern('dr-hatch-floor', 0.55)]));

  // gridlines — hairline, solid, recessive
  tickValues.forEach((value) => {
    root.appendChild(svg('line', {
      class: 'dr-grid', x1: M.left - 8, x2: width - M.right, y1: yOf(value), y2: yOf(value),
    }));
    root.appendChild(svg('text', {
      class: 'dr-axis-label', x: M.left - 12, y: yOf(value) + 4, 'text-anchor': 'end',
      text: fmtUsd(value),
    }));
  });
  root.appendChild(svg('text', {
    class: 'dr-axis-title', x: M.left - 12, y: M.top - 12, 'text-anchor': 'end',
    text: 'USD',
  }));

  laid.forEach((item) => {
    const bar = item.bar;
    const cx = item.x + BAR_W / 2;
    const group = svg('g', { class: 'dr-bar-group' });

    if (bar.measure.value === null) {
      // An honest gap: a hatched full-height slot that cannot be read as a magnitude,
      // labelled in words. Never a zero-height bar sitting on the baseline.
      group.appendChild(svg('rect', {
        class: 'dr-bar--gap', x: item.x, y: M.top, width: BAR_W, height: PLOT_H,
        fill: 'url(#dr-hatch-gap)', rx: 3,
      }));
      group.appendChild(svg('text', {
        class: 'dr-bar__gaplabel', x: cx, y: M.top + PLOT_H - 8, 'text-anchor': 'start',
        transform: 'rotate(-90 ' + cx + ' ' + (M.top + PLOT_H - 8) + ')',
        text: bar.measureLabel,
      }));
    } else {
      const y = yOf(bar.measure.value);
      group.appendChild(svg('rect', {
        class: 'dr-bar' + (bar.measure.isFloor ? ' is-floor' : ''),
        x: item.x, y: y, width: BAR_W, height: Math.max(1, M.top + PLOT_H - y), rx: 4,
        style: '--dr-arm-light:' + bar.light + ';--dr-arm-dark:' + bar.dark,
      }));
      group.appendChild(svg('text', {
        class: 'dr-bar__label', x: cx, y: y - 7, 'text-anchor': 'middle', text: bar.measureLabel,
      }));
      if (bar.dispersion.available) {
        // Whisker = per-attempt cost min–max, a different measure on the same axis.
        // Called out in the legend, the footnote and the table twin.
        const wx = cx;
        group.appendChild(svg('line', {
          class: 'dr-whisker', x1: wx, x2: wx, y1: yOf(bar.dispersion.max), y2: yOf(bar.dispersion.min),
        }));
        [bar.dispersion.min, bar.dispersion.max].forEach((v) => {
          group.appendChild(svg('line', {
            class: 'dr-whisker__cap', x1: wx - 5, x2: wx + 5, y1: yOf(v), y2: yOf(v),
          }));
        });
        group.appendChild(svg('line', {
          class: 'dr-whisker__median', x1: wx - 7, x2: wx + 7,
          y1: yOf(bar.dispersion.median), y2: yOf(bar.dispersion.median),
        }));
      }
    }

    group.appendChild(svg('text', {
      class: 'dr-bar__arm' + (bar.registered ? '' : ' is-unregistered'),
      x: cx, y: M.top + PLOT_H + 16, 'text-anchor': 'middle', text: bar.arm,
    }));
    group.appendChild(svg('text', {
      class: 'dr-bar__n', x: cx, y: M.top + PLOT_H + 30, 'text-anchor': 'middle',
      text: bar.acceptanceDisplay || ('0/' + bar.nRuns),
    }));

    attachTip(group, () => [
      { label: bar.arm, value: bar.blurb, strong: true },
      { label: 'task', value: item.group.label },
      { label: 'cost / accepted outcome', value: bar.measureLabel },
      bar.measure.isFloor ? { label: '', value: 'a floor: at least one leg of the bill is unavailable' } : null,
      bar.measure.reason ? { label: 'why', value: bar.measure.reason } : null,
      { label: 'accepted', value: bar.acceptanceDisplay || 'unavailable' },
      bar.dispersion.available
        ? { label: 'per-attempt cost', value: fmtUsd(bar.dispersion.median) + '  (' + fmtUsd(bar.dispersion.min) + '–' + fmtUsd(bar.dispersion.max) + ', n=' + bar.dispersion.n + ')' }
        : { label: 'per-attempt cost', value: 'unavailable — ' + bar.dispersion.reason },
      { label: 'confidence', value: bar.tier.replace(/_/g, ' ') },
      { label: 'scope', value: bar.scopeLine || 'unavailable' },
    ]);
    root.appendChild(group);
  });

  // Group (task) labels and the band rule under each group.
  panel.groups.forEach((group) => {
    const mid = (group._start + group._end) / 2;
    root.appendChild(svg('line', {
      class: 'dr-group-rule', x1: group._start, x2: group._end,
      y1: M.top + PLOT_H + 40, y2: M.top + PLOT_H + 40,
    }));
    root.appendChild(svg('text', {
      class: 'dr-group__label', x: mid, y: M.top + PLOT_H + 56, 'text-anchor': 'middle', text: group.label,
    }));
    root.appendChild(svg('text', {
      class: 'dr-group__n', x: mid, y: M.top + PLOT_H + 70, 'text-anchor': 'middle',
      text: 'n = ' + group.nRuns + ' runs',
    }));
  });

  root.appendChild(svg('line', {
    class: 'dr-baseline', x1: M.left - 8, x2: width - M.right, y1: M.top + PLOT_H, y2: M.top + PLOT_H,
  }));
  return root;
}

function hatchPattern(id, opacity) {
  return svg('pattern', {
    id: id, width: 6, height: 6, patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)',
  }, [
    svg('rect', { width: 6, height: 6, class: 'dr-hatch__bg', opacity: opacity || 1 }),
    svg('line', { x1: 0, y1: 0, x2: 0, y2: 6, class: 'dr-hatch__line' }),
  ]);
}

/** Legend: identity is never colour-alone, so the swatch always sits beside a label. */
function bandLegend(bands, extraItems) {
  return el('div', { class: 'dr-legend' }, [
    el('ul', { class: 'dr-legend__list' }, bands.map((band) => el('li', { class: 'dr-legend__item', title: band.note }, [
      el('span', { class: 'dr-legend__band', text: band.label }),
      el('span', { class: 'dr-legend__arms' }, ARMS.filter((a) => a.band === band.id).map((a) => el('span', { class: 'dr-legend__arm' }, [
        armSwatch(a.id), el('span', { text: a.id }),
      ]))),
    ]))),
    extraItems ? el('ul', { class: 'dr-legend__marks' }, extraItems.map((item) => el('li', {}, [
      el('span', { class: 'dr-legend__mark ' + item.mark }),
      el('span', { text: item.label }),
    ]))) : null,
  ]);
}

/* ---------------------------------------------------------------- the sections */

function renderClassPanels(model) {
  const section = el('section', { class: 'dr-section', id: 'decision-cards' }, [
    el('h2', { text: 'Decision cards, by task class' }),
    el('p', { class: 'dr-lede' }, [
      'One card per task class. There is deliberately ',
      el('strong', { text: 'no single leaderboard' }),
      ': the arms below belong to three different comparison types — a tier comparison ' +
      'inside one product, a routing-policy comparison inside one product, and a hybrid ' +
      'workflow spanning two — and SPEC §2.1 does not let them share a ranking. Bars are ' +
      'banded by comparison type and drawn in a fixed declared order, never sorted by value.',
    ]),
  ]);

  model.classes.forEach((panel) => {
    const rows = [];
    panel.groups.forEach((group) => group.bars.forEach((bar) => {
      rows.push([
        group.label + ' · ' + bar.arm,
        bandMeta(bar.band).label,
        bar.measureLabel,
        bar.dispersion.available
          ? fmtUsd(bar.dispersion.median) + ' (' + fmtUsd(bar.dispersion.min) + '–' + fmtUsd(bar.dispersion.max) + ')'
          : null,
        bar.acceptanceDisplay,
        bar.nRuns,
        bar.tier.replace(/_/g, ' '),
        bar.scopeLine,
      ]);
    }));

    const card = el('article', { class: 'dr-card' }, [
      el('header', { class: 'dr-card__head' }, [
        el('h3', { class: 'dr-card__title', text: panel.taskClass.replace(/_/g, ' ') }),
        el('span', { class: 'dr-card__tasks', text: panel.tasks.map((t) => t.label).join(' · ') }),
        nBadge(panel.nRuns, 'run'),
      ]),
      figure({
        title: 'Cost per accepted outcome',
        subtitle: 'Bar height is the cost per accepted outcome for the cell. The whisker is a ' +
                  'different measure on the same axis: the min–max of the per-attempt cost, ' +
                  'with a tick at the attempt median.',
        n: panel.nRuns,
        unit: 'run',
        legend: bandLegend(panel.bands, [
          { mark: 'is-whisker', label: 'per-attempt cost, min–max, tick at median' },
          { mark: 'is-floor', label: '≥ marks a floor: at least one leg of the bill is unavailable' },
          { mark: 'is-gap', label: 'hatched slot: no figure — unavailable or undefined, never zero' },
        ]),
        plot: panel.hasAnyValue || panel.groups.length
          ? costChart(panel)
          : el('p', { class: 'dr-empty', text: 'No cost figure is available for any cell in this class.' }),
        table: dataTable(
          ['Task · arm', 'Comparison band', 'Cost / accepted outcome', 'Per-attempt cost, median (min–max)',
           'Accepted', 'Runs', 'Confidence', 'Scope'],
          rows
        ),
        footnote: 'Cost per accepted outcome divides the summed attempt cost of the cell by the ' +
                  'number of accepted outcomes, so a cell that accepted nothing has no value — it ' +
                  'is shown as "no accepted outcome", not as a large number and not as zero.',
      }),
      panel.gaps.length
        ? el('details', { class: 'dr-gaps' }, [
            el('summary', { text: panel.gaps.length + ' cell(s) in this class have no cost figure' }),
            el('ul', {}, panel.gaps.map((gap) => el('li', {}, [
              el('code', { text: gap.arm + ' · ' + taskShort(gap.taskId) }),
              ' — ' + (MEASURE_LABEL[gap.status] || gap.status) +
              (gap.reason ? ': ' + gap.reason : ''),
            ]))),
          ])
        : null,
      el('div', { class: 'dr-card__scopes' }, panel.scopeLines.map((line) => scopeFooter(line, null))),
    ]);
    section.appendChild(card);
  });
  return section;
}

function taskShort(taskId) {
  return String(taskId).length > 34 ? String(taskId).slice(0, 33) + '…' : String(taskId);
}

/* --------------------------------------------------------------- heat matrix */

function renderHeatMatrix(model) {
  const heat = model.heat;
  const grid = el('div', { class: 'dr-heat' });
  const table = el('table', { class: 'dr-heat__table' });
  table.appendChild(el('thead', {}, el('tr', {}, [el('th', { class: 'dr-heat__corner', scope: 'col', text: 'Arm' })].concat(
    heat.tasks.map((t) => el('th', { scope: 'col', class: 'dr-heat__colhead' }, el('span', { text: t.label })))
  ))));

  const body = el('tbody', {});
  heat.rows.forEach((row) => {
    const tr = el('tr', {}, [el('th', { scope: 'row', class: 'dr-heat__rowhead' }, [armSwatch(row.arm), el('span', { text: row.arm })])]);
    row.cells.forEach((cellData) => {
      const td = el('td', { class: 'dr-heat__cell is-' + cellData.state });
      if (cellData.state === 'ran' && cellData.rate !== null) {
        // Sequential = one hue, light→dark. Rate carries the magnitude; the printed
        // fraction carries it again so the cell is never colour-alone.
        td.style.setProperty('--dr-heat-t', cellData.rate.toFixed(3));
        // Past this point the fill is dark enough that near-black text stops clearing
        // the contrast floor, so the label flips to white.
        if (cellData.rate > 0.62) td.classList.add('is-deep');
        td.appendChild(el('span', { class: 'dr-heat__value', text: cellData.display }));
      } else if (cellData.state === 'ran') {
        td.appendChild(el('span', { class: 'dr-heat__value is-missing', text: 'unavailable' }));
      } else {
        td.appendChild(el('span', {
          class: 'dr-heat__value is-missing',
          text: cellData.state === 'not-registered' ? '·' : 'not run',
        }));
      }
      attachTip(td, () => [
        { label: row.arm + ' · ' + taskShort(cellData.taskId), value: armMeta(row.arm).blurb, strong: true },
        { label: 'accepted', value: cellData.state === 'ran' ? (cellData.display || 'unavailable') : cellData.note },
        cellData.tier ? { label: 'confidence', value: cellData.tier } : null,
        cellData.scopeLine ? { label: 'scope', value: cellData.scopeLine } : null,
      ]);
      tr.appendChild(td);
    });
    body.appendChild(tr);
  });
  table.appendChild(body);
  grid.appendChild(table);

  const rows = heat.rows.map((row) => [row.arm].concat(row.cells.map((c) =>
    c.state === 'ran' ? (c.display || 'unavailable') : (c.state === 'not-registered' ? 'not registered' : 'registered, not run')
  )));

  return el('section', { class: 'dr-section', id: 'acceptance-matrix' }, [
    el('h2', { text: 'Acceptance, arm × task' }),
    el('p', { class: 'dr-lede', text:
      'The share of runs that cleared the pre-registered deterministic-first gate. This is a ' +
      'coverage and outcome view, not a ranking: reading down a column compares arms on one ' +
      'task only, and reading across a row says nothing about a workload class (SPEC §5.2).' }),
    figure({
      title: 'Acceptance rate by arm and task',
      subtitle: 'Darker means a larger share of runs accepted. A cell that ran and accepted ' +
                'nothing is a real 0/n; a cell that never ran says so; a cell that was never ' +
                'registered for that task is left dotted.',
      n: heat.nRuns,
      unit: 'run',
      legend: el('div', { class: 'dr-legend dr-legend--heat' }, [
        el('span', { class: 'dr-heatkey' }, [
          el('span', { text: '0/n' }),
          el('span', { class: 'dr-heatkey__ramp' }),
          el('span', { text: 'n/n' }),
        ]),
        el('span', { class: 'dr-legend__mark is-notrun' }), el('span', { text: 'registered, not run' }),
        el('span', { class: 'dr-legend__mark is-notreg' }), el('span', { text: 'not registered for that task' }),
      ]),
      plot: grid,
      table: dataTable(['Arm'].concat(heat.tasks.map((t) => t.label)), rows),
      footnote: heat.basis ? 'Acceptance basis: ' + heat.basis : null,
    }),
  ]);
}

/* -------------------------------------------------------------- effort panel */

const VERDICT_KIND = {
  within_predicted_band: 'good',
  above_predicted_band: 'good',
  below_predicted_band: 'warn',
  direction_refuted: 'bad',
  gate_parity_refuted: 'bad',
  exploratory_not_graded: 'neutral',
  not_gradable: 'neutral',
};

const VERDICT_BLURB = {
  within_predicted_band: 'the observed reduction fell inside the registered band',
  above_predicted_band: 'the observed reduction was larger than the registered band predicted',
  below_predicted_band: 'the observed reduction was smaller than the registered band predicted',
  direction_refuted: 'the cheaper effort level was not cheaper per accepted outcome',
  gate_parity_refuted: 'the registration required the same gates to pass; they did not',
  exploratory_not_graded: 'this task class is outside the registration’s declared scope — reported, not graded',
  not_gradable: 'not enough data in this dataset to grade the pair',
};

function renderEffortPanel(model) {
  const panel = model.effort;
  if (!panel) return null;
  const reg = panel.registration;
  const band = reg.band;

  const rowH = 46;
  const width = 760;
  const left = 190;
  const right = 150;
  const plotW = width - left - right;
  const height = 46 + panel.byTask.length * rowH + 34;
  const lo = panel.domain.lo;
  const hi = panel.domain.hi;
  const xOf = (pct) => left + ((pct - lo) / (hi - lo)) * plotW;

  const root = svg('svg', {
    class: 'dr-chart dr-chart--effort', viewBox: '0 0 ' + width + ' ' + height, role: 'img',
    'aria-label': 'Observed cost-per-accepted-outcome reduction per task against the registered prediction band',
  });
  root.appendChild(svg('defs', {}, [hatchPattern('dr-hatch-band', 0.4)]));

  if (band) {
    root.appendChild(svg('rect', {
      class: 'dr-predband', x: xOf(band.low), y: 30, width: Math.max(0, xOf(band.high) - xOf(band.low)),
      height: height - 30 - 30,
    }));
    root.appendChild(svg('text', {
      class: 'dr-predband__label', x: (xOf(band.low) + xOf(band.high)) / 2, y: 22, 'text-anchor': 'middle',
      text: 'registered prediction ' + fmtPct(band.low, 0) + '–' + fmtPct(band.high, 0),
    }));
  }

  [lo, 0, hi].concat(band ? [band.low, band.high] : []).forEach((value) => {
    if (value < lo || value > hi) return;
    root.appendChild(svg('line', {
      class: value === 0 ? 'dr-zeroline' : 'dr-grid', x1: xOf(value), x2: xOf(value), y1: 30, y2: height - 30,
    }));
    root.appendChild(svg('text', {
      class: 'dr-axis-label', x: xOf(value), y: height - 14, 'text-anchor': 'middle', text: fmtPct(value, 0),
    }));
  });
  root.appendChild(svg('text', {
    class: 'dr-axis-title', x: left, y: height - 2, 'text-anchor': 'start',
    text: 'reduction in cost per accepted outcome, medium vs high effort',
  }));

  panel.byTask.forEach((row, i) => {
    const y = 46 + i * rowH;
    const group = svg('g', { class: 'dr-effort-row' + (row.inScope ? '' : ' is-exploratory') });
    group.appendChild(svg('text', {
      class: 'dr-effort__task', x: left - 12, y: y + 16, 'text-anchor': 'end', text: row.label,
    }));
    if (row.reductionPct === null) {
      group.appendChild(svg('text', {
        class: 'dr-effort__gap', x: xOf(Math.max(lo, 0)) + 6, y: y + 16, 'text-anchor': 'start',
        text: row.deltaReason || 'no reduction figure — ' + (MEASURE_LABEL[row.verdict] || 'not gradable'),
      }));
    } else {
      const zero = xOf(0);
      const value = xOf(row.reductionPct);
      group.appendChild(svg('rect', {
        class: 'dr-effort__bar' + (row.inScope ? '' : ' is-exploratory'),
        x: Math.min(zero, value), y: y + 4, width: Math.max(2, Math.abs(value - zero)), height: 18, rx: 4,
      }));
      group.appendChild(svg('text', {
        class: 'dr-effort__value', x: value + (row.reductionPct >= 0 ? 8 : -8), y: y + 18,
        'text-anchor': row.reductionPct >= 0 ? 'start' : 'end', text: fmtPct(row.reductionPct),
      }));
    }
    attachTip(group, () => [
      { label: row.label, value: (row.taskClass || '').replace(/_/g, ' '), strong: true },
      { label: 'verdict', value: row.verdict.replace(/_/g, ' ') + ' — ' + (VERDICT_BLURB[row.verdict] || '') },
      { label: 'reduction', value: row.reductionPct === null ? (row.deltaReason || 'unavailable') : fmtPct(row.reductionPct) },
      row.gateParity ? { label: 'gate parity', value: (row.gateParity.holds ? 'holds' : 'does not hold') + ' — ' + row.gateParity.basis } : null,
    ].concat(row.arms.map((a) => ({
      label: a.arm, value: (a.ecst === null ? 'unavailable' : fmtUsd(a.ecst)) + ' per accepted outcome, accepted ' + (a.acceptance || 'unavailable'),
    }))).concat([
      row.deltaConfidence ? { label: 'confidence', value: row.deltaConfidence } : null,
    ]));
    root.appendChild(group);
  });

  const tableRows = panel.byTask.map((row) => {
    const high = row.arms.find((a) => a.arm === 'C3');
    const med = row.arms.find((a) => a.arm === 'C3-med');
    return [
      row.label,
      row.taskClass ? row.taskClass.replace(/_/g, ' ') : null,
      high && high.ecst !== null ? fmtUsd(high.ecst) : 'unavailable',
      med && med.ecst !== null ? fmtUsd(med.ecst) : 'unavailable',
      row.reductionPct === null ? (row.deltaReason || 'unavailable') : fmtPct(row.reductionPct),
      row.gateParity ? (row.gateParity.holds ? 'holds' : 'does not hold') : 'unavailable',
      row.verdict.replace(/_/g, ' '),
      (high && high.scopeLine) || (med && med.scopeLine) || null,
    ];
  });

  return el('section', { class: 'dr-section', id: 'effort-panel' }, [
    el('h2', { text: 'Effort panel — the registered high-vs-medium prediction' }),
    el('p', { class: 'dr-lede' }, [
      'A within-product comparison of two effort levels on identical tasks, prompts and gates. ',
      'The prediction was written down ',
      el('strong', { text: 'before' }),
      ' any run and is graded here against what the runs show — ' +
      'including where it was wrong, which the registration committed to publishing either way.',
    ]),
    el('div', { class: 'dr-prereg' }, [
      el('div', { class: 'dr-prereg__head' }, [
        chip(reg.id, 'prereg'),
        reg.registered ? el('span', { class: 'dr-prereg__date', text: 'registered ' + reg.registered }) : null,
        reg.file ? el('code', { class: 'dr-prereg__file', text: reg.file }) : null,
        chip('grading: ' + panel.status, panel.status === 'complete' ? 'good' : 'neutral'),
        reg.publishEitherWay ? chip('published either way', 'neutral') : null,
      ]),
      reg.prediction ? el('blockquote', { class: 'dr-prereg__text', text: reg.prediction }) : null,
      reg.scopeNote ? el('p', { class: 'dr-prereg__note', text: 'Scope condition: ' + reg.scopeNote }) : null,
      reg.attributionNote ? el('p', { class: 'dr-prereg__note', text: 'Attribution: ' + reg.attributionNote }) : null,
      el('ul', { class: 'dr-tally' }, Object.keys(panel.tally).sort().map((verdict) => el('li', {}, [
        chip(panel.tally[verdict] + ' × ' + verdict.replace(/_/g, ' '), VERDICT_KIND[verdict] || 'neutral', VERDICT_BLURB[verdict] || null),
      ]))),
    ]),
    figure({
      title: 'Observed reduction against the registered band',
      subtitle: 'Each bar is one task. The shaded column is the band the registration predicted; ' +
                'a bar landing outside it is a miss and is labelled as one.',
      n: panel.nGraded,
      unit: 'graded task',
      legend: el('div', { class: 'dr-legend' }, [
        el('span', { class: 'dr-legend__mark is-predband' }), el('span', { text: 'registered prediction band' }),
        el('span', { class: 'dr-legend__mark is-effort' }), el('span', { text: 'observed reduction, in registered scope' }),
        el('span', { class: 'dr-legend__mark is-exploratory' }), el('span', { text: 'outside registered scope — shown, not graded' }),
      ]),
      plot: root,
      table: dataTable(
        ['Task', 'Class', 'High effort, cost / accepted outcome', 'Medium effort, cost / accepted outcome',
         'Reduction', 'Gate parity', 'Verdict', 'Scope'],
        tableRows
      ),
      footnote: panel.note,
    }),
    panel.nExploratory
      ? el('p', { class: 'dr-caveat', text:
          panel.nExploratory + ' task(s) sit outside the registration’s declared scope and are shown ' +
          'without a verdict. They are not evidence for or against the prediction.' })
      : null,
  ]);
}

/* ------------------------------------------------------------- routing panel */

const OUTCOME_KIND = {
  prediction_supported: 'good',
  prediction_refuted: 'bad',
  mixed: 'warn',
  not_yet_run: 'neutral',
  not_gradable: 'neutral',
};

function renderRoutingPanel(model) {
  const routing = model.routing;
  if (!routing || (!routing.escalation && !routing.bills.length)) return null;
  const section = el('section', { class: 'dr-section', id: 'routing' }, [
    el('h2', { text: 'Routing — what the policy did, and what it billed' }),
    el('p', { class: 'dr-lede', text:
      'Routing arms are policies, not models. What follows describes what a policy did on one ' +
      'task under pinned conditions and what each leg of the resulting bill cost. It ranks ' +
      'nothing and attributes nothing to model capability, and a two-leg bill with one ' +
      'unpriced leg is reported as a floor, never completed by inference.' }),
  ]);

  if (routing.escalation) section.appendChild(renderEscalation(routing.escalation));
  routing.bills.forEach((bill) => section.appendChild(renderBill(bill)));
  return section;
}

function renderEscalation(esc) {
  const reg = esc.registration;
  const card = el('article', { class: 'dr-card dr-card--routing' }, [
    el('header', { class: 'dr-card__head' }, [
      el('h3', { class: 'dr-card__title', text: 'Escalation probe' }),
      el('span', { class: 'dr-card__tasks', text: (esc.label || 'no probe task') + (esc.taskClass ? ' · ' + esc.taskClass.replace(/_/g, ' ') : '') }),
      nBadge(esc.nProbeRuns, 'probe run'),
    ]),
    el('div', { class: 'dr-prereg' }, [
      el('div', { class: 'dr-prereg__head' }, [
        chip(reg.id, 'prereg'),
        reg.registered ? el('span', { class: 'dr-prereg__date', text: 'registered ' + reg.registered }) : null,
        reg.file ? el('code', { class: 'dr-prereg__file', text: reg.file }) : null,
        reg.publishEitherWay ? chip('published either way', 'neutral') : null,
      ]),
      reg.prediction ? el('blockquote', { class: 'dr-prereg__text', text: reg.prediction }) : null,
      reg.selectionNote ? el('p', { class: 'dr-prereg__note', text: 'Selection: ' + reg.selectionNote }) : null,
    ]),
    el('div', { class: 'dr-outcome' }, [
      el('div', { class: 'dr-outcome__main' }, [
        el('span', { class: 'dr-outcome__label', text: 'Outcome' }),
        chip(esc.outcome.replace(/_/g, ' '), OUTCOME_KIND[esc.outcome] || 'neutral'),
      ]),
      esc.outcomeBasis ? el('p', { class: 'dr-outcome__basis', text: esc.outcomeBasis }) : null,
      // The two conditions are reported separately on purpose: the gate result and the
      // branch firing are different observations, and a single verdict would hide which
      // half of the prediction carried it.
      el('ul', { class: 'dr-outcome__parts' }, [
        el('li', {}, [
          el('span', { class: 'dr-outcome__part', text: 'economical solo arm (' + (esc.economicalArm || '—') + ') at the gate' }),
          chip(esc.economicalGate.replace(/_/g, ' '), esc.economicalGate === 'failed' ? 'warn' : 'neutral'),
        ]),
        el('li', {}, [
          el('span', { class: 'dr-outcome__part', text: 'escalation branch on the probe arm (' + (esc.probeArm || '—') + ')' }),
          chip(esc.branch.replace(/_/g, ' '), esc.branch === 'observed' ? 'good' : 'neutral'),
          esc.nEscalated !== null ? el('span', { class: 'dr-outcome__count', text: esc.nEscalated + ' of ' + (esc.nProbeRuns === null ? '?' : esc.nProbeRuns) + ' runs escalated' }) : null,
        ]),
      ]),
    ]),
    esc.economicalSolo ? cellSummary('Economical solo arm — ' + (esc.economicalArm || ''), esc.economicalSolo) : null,
    esc.probeCell ? cellSummary('Escalation arm — ' + (esc.probeArm || ''), esc.probeCell) : null,
  ]);

  if (esc.trace.length) {
    const rows = [];
    esc.trace.forEach((run) => {
      run.legs.forEach((leg, i) => {
        rows.push([
          i === 0 ? 'run ' + run.index : '',
          leg.legId + (leg.role ? ' (' + leg.role + ')' : ''),
          leg.selector,
          leg.costLabel === 'unavailable' ? null : leg.costLabel,
          leg.costBasis,
          i === 0 ? (run.intention || 'unavailable') + ' → ' + (run.completed || 'unavailable') : '',
          i === 0 ? (run.fired ? 'escalated' : 'no escalation') : '',
        ]);
      });
    });
    card.appendChild(figure({
      title: 'Escalation trace, run by run',
      subtitle: 'Where each run intended to route, where it finished, and every leg it billed on ' +
                'the way. A leg the product does not price stays unpriced.',
      n: esc.trace.length,
      unit: 'run',
      plot: el('ol', { class: 'dr-trace' }, esc.trace.map((run) => el('li', { class: 'dr-trace__run' }, [
        el('div', { class: 'dr-trace__head' }, [
          el('span', { class: 'dr-trace__idx', text: 'run ' + run.index }),
          el('span', { class: 'dr-trace__route' }, [
            chip(run.intention || 'unavailable', 'route'),
            el('span', { class: 'dr-trace__arrow', text: '→' }),
            chip(run.completed || 'unavailable', run.fired ? 'route-escalated' : 'route'),
          ]),
          run.fired ? chip('escalation fired', 'warn') : chip('no escalation', 'neutral'),
        ]),
        el('ul', { class: 'dr-trace__legs' }, run.legs.map((leg) => el('li', {}, [
          el('span', { class: 'dr-trace__leg', text: leg.legId }),
          el('span', { class: 'dr-trace__selector', text: leg.selector || 'unavailable' }),
          el('span', {
            class: 'dr-trace__cost' + (leg.cost.available ? '' : ' is-unavailable'),
            text: leg.cost.available ? fmtUsd(leg.cost.median) : 'unavailable',
          }),
        ]))),
        el('ul', { class: 'dr-trace__gates' }, (run.gates || []).map((gate) => el('li', {}, [
          chip(gate.gate + ': ' + gate.status, gate.status === 'pass' ? 'good' : 'bad',
               (gate.failed_checks || []).length ? 'failed: ' + gate.failed_checks.join(', ') : null),
        ]))),
      ]))),
      table: dataTable(
        ['Run', 'Leg', 'Selector', 'Cost', 'Cost basis', 'Route', 'Escalation'],
        rows
      ),
      footnote: esc.note,
    }));
  }
  return card;
}

function cellSummary(title, cell) {
  const ecst = readMeasure(cell.ecst_usd);
  return el('div', { class: 'dr-cellsummary' }, [
    el('h4', { text: title }),
    el('dl', { class: 'dr-kv' }, [
      el('dt', { text: 'accepted' }), el('dd', { text: cell.acceptance || 'unavailable' }),
      el('dt', { text: 'cost / accepted outcome' }),
      el('dd', { class: ecst.value === null ? 'is-unavailable' : null, text: measureLabel(ecst) }),
      ecst.reason ? el('dt', { text: 'why' }) : null,
      ecst.reason ? el('dd', { text: ecst.reason }) : null,
    ]),
    scopeFooter(cell.scope_line, ecst.status === 'derived' ? 'derived' : ecst.status),
  ]);
}

function renderBill(bill) {
  const rows = bill.rows.map((leg) => [
    leg.legId + (leg.role ? ' (' + leg.role + ')' : ''),
    leg.selector,
    leg.costBasis,
    leg.cost.available ? fmtUsd(leg.cost.median) : null,
    leg.cost.available ? fmtUsd(leg.cost.min) + '–' + fmtUsd(leg.cost.max) : null,
    leg.nLegs,
    leg.confidence,
    leg.usage.filter((u) => u.value !== null).map((u) => u.tokenClass.replace(/_tokens$/, '') + ' ' + fmtInt(u.value)).join(', ') || null,
  ]);

  const unpriced = bill.rows.filter((leg) => !leg.cost.available);
  return el('article', { class: 'dr-card dr-card--bill' }, [
    el('header', { class: 'dr-card__head' }, [
      el('h3', { class: 'dr-card__title' }, [armSwatch(bill.arm), el('span', { text: bill.arm + ' — itemised bill' })]),
      el('span', { class: 'dr-card__tasks', text: bill.label + (bill.taskClass ? ' · ' + bill.taskClass.replace(/_/g, ' ') : '') }),
      nBadge(bill.nRuns, 'run'),
    ]),
    el('p', { class: 'dr-card__lede', text: bill.color.blurb }),
    el('div', { class: 'dr-billrows' }, bill.rows.map((leg) => el('div', { class: 'dr-billrow' + (leg.cost.available ? '' : ' is-unavailable') }, [
      el('div', { class: 'dr-billrow__id' }, [
        el('span', { class: 'dr-billrow__leg', text: leg.legId }),
        leg.role ? el('span', { class: 'dr-billrow__role', text: leg.role }) : null,
      ]),
      el('div', { class: 'dr-billrow__who' }, [
        el('span', { class: 'dr-billrow__selector', text: leg.selector || 'unavailable' }),
        el('span', { class: 'dr-billrow__basis', text: leg.costBasis || 'unavailable' }),
      ]),
      el('div', { class: 'dr-billrow__cost' }, [
        el('span', { class: 'dr-billrow__amount', text: leg.cost.available ? fmtUsd(leg.cost.median) : 'unavailable' }),
        el('span', {
          class: 'dr-billrow__range',
          text: leg.cost.available
            ? fmtUsd(leg.cost.min) + '–' + fmtUsd(leg.cost.max) + ' across ' + leg.nLegs + ' leg' + (leg.nLegs === 1 ? '' : 's')
            : leg.cost.reason,
        }),
      ]),
      tierChip(leg.confidence),
    ]))),
    el('div', { class: 'dr-billtotal' + (bill.total.isFloor || unpriced.length ? ' is-floor' : '') }, [
      el('span', { class: 'dr-billtotal__label', text: 'Cost per accepted outcome' }),
      el('span', { class: 'dr-billtotal__value', text: measureLabel(bill.total) }),
      unpriced.length
        ? el('span', { class: 'dr-billtotal__note', text:
            unpriced.length + ' of ' + bill.rows.length + ' legs are unpriced, so the total is a ' +
            'lower bound. The missing leg is not estimated from the priced one.' })
        : null,
    ]),
    figure({
      title: 'Legs, itemised',
      n: bill.nRuns,
      unit: 'run',
      plot: el('div', { class: 'dr-scroll' }, dataTable(
        ['Leg', 'Selector', 'Cost basis', 'Median cost', 'Range', 'Legs', 'Confidence', 'Reported usage'],
        rows
      )),
      footnote: bill.basis,
    }),
    scopeFooter(bill.scopeLine, bill.tier),
  ]);
}

/* --------------------------------------------------------------- coverage */

function renderCoverage(model) {
  const cov = model.coverage;
  if (!cov) return null;
  const rows = cov.rows.map((row) => [
    row.label,
    row.taskClass ? row.taskClass.replace(/_/g, ' ') : null,
    row.registered.join(' ') || null,
    row.observed.join(' ') || null,
    row.missing.join(' ') || '—',
    row.companionObserved.join(' ') || '—',
    row.unregistered.join(' ') || '—',
  ]);
  const nMissing = cov.rows.reduce((s, r) => s + r.missing.length, 0);
  return el('section', { class: 'dr-section', id: 'coverage' }, [
    el('h2', { text: 'Coverage against the registered matrix' }),
    el('p', { class: 'dr-lede', text:
      'Which arms were registered for each task before the batch ran, and which actually ' +
      'produced runs. A registered arm with no runs is listed here rather than dropped, ' +
      'because a quietly absent cell is indistinguishable from a cell that was never planned.' }),
    el('p', { class: 'dr-meta-line' }, [
      chip(cov.complete ? 'coverage complete' : nMissing + ' registered cell(s) missing', cov.complete ? 'good' : 'warn'),
      cov.source ? el('span', { class: 'dr-meta-line__src', text: 'source: ' + cov.source } ) : null,
    ]),
    figure({
      title: 'Registered vs observed arms',
      n: cov.rows.length,
      unit: 'task',
      plot: el('div', { class: 'dr-scroll' }, dataTable(
        ['Task', 'Class', 'Registered', 'Observed', 'Missing', 'Companion observed', 'Unregistered'],
        rows
      )),
      footnote: cov.tasksNotInRegistry.length
        ? 'Runs present for tasks not in the registry: ' + cov.tasksNotInRegistry.join(', ')
        : null,
    }),
  ]);
}

/* ---------------------------------------------------------------- the header */

function renderHeader(model) {
  const meta = model.meta;
  const head = el('header', { class: 'dr-head' });

  if (meta.synthetic) {
    head.appendChild(el('div', { class: 'dr-banner dr-banner--synthetic', role: 'note' }, [
      el('strong', { text: 'SYNTHETIC FIXTURE — not a measurement. ' }),
      el('span', { text: meta.syntheticNotice || 'Every figure below is fabricated to exercise the renderer.' }),
    ]));
  }
  head.appendChild(el('div', { class: 'dr-banner dr-banner--status', role: 'note' }, [
    chip(meta.status, meta.status === 'AUTHORITATIVE' ? 'good' : 'warn'),
    el('span', { text: meta.cpFindingsGate
      ? meta.cpFindingsGate.replace(/\*\*/g, '')
      : 'No figure here may appear in external-facing material before CP-FINDINGS.' }),
  ]));
  head.appendChild(el('dl', { class: 'dr-meta' }, [
    el('dt', { text: 'dataset' }), el('dd', { text: meta.sourceDataset || 'unavailable' }),
    el('dt', { text: 'schema' }), el('dd', { text: meta.schema || 'unavailable' }),
    el('dt', { text: 'runs' }), el('dd', { text: String(meta.nRuns) }),
    el('dt', { text: 'cells' }), el('dd', { text: String(meta.nCells) }),
    el('dt', { text: 'manifest' }), el('dd', { text: meta.manifestRef || 'unavailable' }),
    el('dt', { text: 'loaded rate' }),
    el('dd', { text: meta.loadedRate === null ? 'unavailable' : '$' + meta.loadedRate.toFixed(2) + ' / minute (declared input)' }),
  ]));
  if (meta.note) head.appendChild(el('p', { class: 'dr-note', text: meta.note }));
  if (meta.screeningNote) head.appendChild(el('p', { class: 'dr-note dr-note--screening', text: meta.screeningNote }));
  return head;
}

function renderEmptyState(reason) {
  return el('div', { class: 'dr-empty-state' }, [
    el('h2', { text: 'No decision table loaded' }),
    el('p', { text: reason }),
    el('p', { text:
      'This page renders whatever decision table it is pointed at and ships with none. ' +
      'Pointing it at a real dataset is gated by CP-FINDINGS; until then, use the synthetic ' +
      'fixture to review the rendering.' }),
    el('pre', { class: 'dr-empty-state__cmd', text:
      '.venv/bin/python -m harness.telemetry.summarize <batch-dir> --out-dir report/<batchN>\n' +
      'cp report/<batchN>/decision-table.json docs/assets/data/decision-table.json' }),
    el('p', { class: 'dr-empty-state__hint', text:
      'docs/assets/data/ is gitignored, so a real table can be rendered locally without ' +
      'any number reaching the repository or the published site.' }),
  ]);
}

/* -------------------------------------------------------------------- render */

function render(root, table) {
  root.textContent = '';
  root.classList.add('dr-root');
  const model = buildViewModel(table);
  if (!model.ok) {
    root.appendChild(renderEmptyState(model.reason));
    return model;
  }
  root.appendChild(renderHeader(model));
  const nav = el('nav', { class: 'dr-nav', 'aria-label': 'Sections' }, [
    el('a', { href: '#decision-cards', text: 'Decision cards' }),
    el('a', { href: '#acceptance-matrix', text: 'Acceptance' }),
    model.effort ? el('a', { href: '#effort-panel', text: 'Effort panel' }) : null,
    model.routing && (model.routing.escalation || model.routing.bills.length) ? el('a', { href: '#routing', text: 'Routing' }) : null,
    model.coverage ? el('a', { href: '#coverage', text: 'Coverage' }) : null,
  ]);
  root.appendChild(nav);
  root.appendChild(renderClassPanels(model));
  root.appendChild(renderHeatMatrix(model));
  const effort = renderEffortPanel(model);
  if (effort) root.appendChild(effort);
  const routing = renderRoutingPanel(model);
  if (routing) root.appendChild(routing);
  const coverage = renderCoverage(model);
  if (coverage) root.appendChild(coverage);
  return model;
}

/**
 * Where to load the table from, in order: an explicit ?src=, the mount point's
 * data-src, then the conventional (gitignored) local path.
 *
 * Only same-origin relative paths are accepted. The page must not be turnable into a
 * fetch against an external service by a crafted link, and the workshop material
 * declares that it talks to no external service.
 */
function resolveSource(search, mount) {
  const params = new URLSearchParams(search || '');
  const requested = params.get('src');
  if (requested) {
    const safe = /^[A-Za-z0-9._~/-]+$/.test(requested) && !requested.startsWith('//') && requested.indexOf('..') === -1;
    if (safe) return { src: requested, origin: 'query' };
    return { src: null, origin: 'query', rejected: requested };
  }
  const attr = mount && mount.getAttribute && mount.getAttribute('data-src');
  if (attr) return { src: attr, origin: 'attribute' };
  return { src: 'assets/data/decision-table.json', origin: 'default' };
}

function mount() {
  const root = document.getElementById('decision-report');
  if (!root) return;
  const resolved = resolveSource(window.location.search, root);
  if (!resolved.src) {
    root.appendChild(renderEmptyState(
      'The requested source "' + resolved.rejected + '" is not a same-origin relative path, so it ' +
      'was not loaded. This page never fetches from an external service.'));
    return;
  }
  fetch(resolved.src, { cache: 'no-store' })
    .then((res) => {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.json();
    })
    .then((table) => render(root, table))
    .catch((err) => {
      root.textContent = '';
      root.appendChild(renderEmptyState(
        'Could not load "' + resolved.src + '" (' + err.message + ').'));
    });
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount);
  } else {
    mount();
  }
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    ARMS: ARMS,
    BANDS: BANDS,
    armMeta: armMeta,
    armOrder: armOrder,
    buildViewModel: buildViewModel,
    fmtUsd: fmtUsd,
    fmtPct: fmtPct,
    measureLabel: measureLabel,
    readMeasure: readMeasure,
    readDispersion: readDispersion,
    resolveSource: resolveSource,
    ticks: ticks,
  };
}
