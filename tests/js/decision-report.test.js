/*
 * Tests for the report page's view-model layer, under bare node: no browser, no DOM, no
 * npm dependencies. That is the point of splitting buildViewModel() out of the renderer
 * — the decisions that matter (is this a number, a floor, or an honest gap? are the arms
 * in declared order? does a missing cell survive to the page?) are testable without a
 * headless browser, so they are actually tested rather than eyeballed.
 *
 * Run directly:  node tests/js/decision-report.test.js
 * Or via the suite: python -m unittest tests.test_report_page
 */
'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const report = require(path.join(ROOT, 'docs', 'assets', 'decision-report.js'));
const FIXTURE = path.join(ROOT, 'tests', 'fixtures', 'decision-table-SYNTHETIC.json');
const table = JSON.parse(fs.readFileSync(FIXTURE, 'utf8'));

const tests = [];
function test(name, fn) { tests.push([name, fn]); }

/* ------------------------------------------------------- the fixture is synthetic */

test('the fixture announces itself as synthetic in the payload, not just the filename', () => {
  assert.strictEqual(table.synthetic, true);
  assert.ok(/SYNTHETIC/.test(table.SYNTHETIC || ''), 'expected a SYNTHETIC marker key');
  assert.ok(/SYNTHETIC/.test(table.synthetic_notice || ''));
  assert.ok(/SYNTHETIC/.test(table.source_dataset || ''),
    'the dataset label must not look like a real results/ directory');
});

test('the header surfaces the synthetic notice so a screenshot cannot hide it', () => {
  const model = report.buildViewModel(table);
  assert.strictEqual(model.meta.synthetic, true);
  assert.ok(model.meta.syntheticNotice.length > 40);
});

/* --------------------------------------------------------------- no leaderboard */

test('bars keep the declared arm order and are never sorted by value', () => {
  const model = report.buildViewModel(table);
  model.classes.forEach((panel) => {
    panel.groups.forEach((group) => {
      const orders = group.bars.map((b) => report.armOrder(b.arm));
      const sorted = orders.slice().sort((a, b) => a - b);
      assert.deepStrictEqual(orders, sorted,
        'arms out of declared order in ' + panel.taskClass + '/' + group.taskId);
    });
  });
});

test('a cheaper arm never floats to the front of its group', () => {
  const model = report.buildViewModel(table);
  const anyOutOfCostOrder = model.classes.some((panel) => panel.groups.some((group) => {
    const values = group.bars.map((b) => b.measure.value).filter((v) => v !== null);
    return values.some((v, i) => i > 0 && v < values[i - 1]);
  }));
  assert.ok(anyOutOfCostOrder,
    'the fixture should contain at least one group whose bars are NOT in cost order — ' +
    'otherwise this test cannot distinguish declared order from a value sort');
});

test('every bar is tagged with the comparison band it belongs to', () => {
  const model = report.buildViewModel(table);
  const known = report.BANDS.map((b) => b.id);
  model.classes.forEach((panel) => panel.groups.forEach((group) => group.bars.forEach((bar) => {
    assert.ok(known.indexOf(bar.band) !== -1, 'unknown band ' + bar.band + ' for ' + bar.arm);
  })));
});

test('a class panel lists more than one band, so the gap is load-bearing', () => {
  const model = report.buildViewModel(table);
  const multi = model.classes.filter((p) => p.bands.length > 1);
  assert.ok(multi.length >= 1, 'expected at least one class spanning several comparison bands');
});

/* --------------------------------------------- unavailable is never zero or blank */

test('a cell with no cost renders in words, never as a number', () => {
  const model = report.buildViewModel(table);
  let seen = 0;
  model.classes.forEach((panel) => panel.groups.forEach((group) => group.bars.forEach((bar) => {
    if (bar.measure.value !== null) return;
    seen += 1;
    assert.ok(/unavailable|no accepted outcome/.test(bar.measureLabel),
      'gap rendered as "' + bar.measureLabel + '"');
    assert.ok(!/\$/.test(bar.measureLabel), 'a gap must not render a dollar figure');
    assert.notStrictEqual(bar.measure.value, 0);
  })));
  assert.ok(seen >= 2, 'the fixture must exercise the gap path; saw ' + seen);
});

test('an unavailable cost is distinguished from an undefined ratio', () => {
  const model = report.buildViewModel(table);
  const statuses = {};
  model.classes.forEach((panel) => panel.groups.forEach((group) => group.bars.forEach((bar) => {
    if (bar.measure.value === null) statuses[bar.measure.status] = true;
  })));
  assert.ok(statuses.unavailable, 'expected a cell whose cost the product does not expose');
  assert.ok(statuses.undefined,
    'expected a cell that ran, accepted nothing, and therefore has no ratio — a different ' +
    'state from an unavailable cost');
});

test('the cell that accepted nothing says so instead of showing a cost', () => {
  const model = report.buildViewModel(table);
  const bars = [];
  model.classes.forEach((p) => p.groups.forEach((g) => g.bars.forEach((b) => bars.push(b))));
  const zeroAccept = bars.filter((b) => b.accepted === 0);
  assert.ok(zeroAccept.length >= 1, 'the fixture must contain a cell that accepted nothing');
  zeroAccept.forEach((bar) => {
    assert.strictEqual(bar.measure.value, null);
    assert.strictEqual(bar.measureLabel, 'no accepted outcome');
  });
});

test('a partial bill reads as a floor, not as a total', () => {
  const model = report.buildViewModel(table);
  const floors = [];
  model.classes.forEach((p) => p.groups.forEach((g) => g.bars.forEach((b) => {
    if (b.measure.isFloor) floors.push(b);
  })));
  assert.ok(floors.length >= 1, 'the fixture must contain a cell with an unpriced leg');
  floors.forEach((bar) => {
    assert.ok(bar.measureLabel.indexOf('≥') === 0, 'floor label was "' + bar.measureLabel + '"');
    assert.strictEqual(bar.tier, 'derived_floor');
  });
});

test('readMeasure never invents a value for a missing slot', () => {
  assert.strictEqual(report.readMeasure(undefined).value, null);
  assert.strictEqual(report.readMeasure({}).value, null);
  assert.strictEqual(report.readMeasure({ value: null, status: 'unavailable' }).value, null);
  assert.strictEqual(report.readMeasure({ value: 0, status: 'derived' }).value, 0,
    'a genuine measured zero must survive — the rule is "never impute", not "never show 0"');
});

test('formatting a missing number yields nothing to print, not "$0"', () => {
  assert.strictEqual(report.fmtUsd(null), null);
  assert.strictEqual(report.fmtUsd(undefined), null);
  assert.strictEqual(report.fmtUsd(NaN), null);
  assert.strictEqual(report.fmtUsd(0), '$0.00');
});

/* -------------------------------------------------------- scope and n, everywhere */

test('every bar carries a scope line and a confidence tier', () => {
  const model = report.buildViewModel(table);
  model.classes.forEach((panel) => panel.groups.forEach((group) => group.bars.forEach((bar) => {
    assert.ok(bar.scopeLine && bar.scopeLine.length > 10,
      'missing scope line on ' + group.taskId + '/' + bar.arm);
    assert.ok(bar.tier, 'missing confidence tier on ' + group.taskId + '/' + bar.arm);
  })));
});

test('every group and every class reports an n', () => {
  const model = report.buildViewModel(table);
  model.classes.forEach((panel) => {
    assert.ok(panel.nRuns > 0, panel.taskClass + ' has no run count');
    panel.groups.forEach((group) => assert.ok(group.nRuns > 0, group.taskId + ' has no run count'));
  });
});

test('a cell with an unpriced leg still reports the dispersion it does have', () => {
  const model = report.buildViewModel(table);
  const bills = model.routing.bills;
  assert.ok(bills.length >= 1);
  const withGap = bills.find((b) => b.rows.some((r) => !r.cost.available));
  assert.ok(withGap, 'expected a multi-leg bill with an unpriced leg');
  assert.ok(withGap.rows.some((r) => r.cost.available), 'expected the other leg to be priced');
  const unpriced = withGap.rows.find((r) => !r.cost.available);
  assert.strictEqual(unpriced.costLabel, 'unavailable');
  assert.ok(unpriced.cost.reason, 'an unpriced leg must carry the reason it is unpriced');
});

/* --------------------------------------------------------------- heat matrix */

test('the matrix separates "did not run" from "ran and accepted nothing"', () => {
  const model = report.buildViewModel(table);
  const states = {};
  model.heat.rows.forEach((row) => row.cells.forEach((c) => { states[c.state] = (states[c.state] || 0) + 1; }));
  assert.ok(states.ran > 0);
  assert.ok(states['not-run'] > 0,
    'the fixture must contain a registered arm with no runs, or this distinction is untested');
  assert.ok(states['not-registered'] > 0,
    'the fixture must contain an arm not registered for some task');
  const zero = [];
  model.heat.rows.forEach((row) => row.cells.forEach((c) => { if (c.state === 'ran' && c.rate === 0) zero.push(c); }));
  assert.ok(zero.length >= 1, 'expected a real 0/n cell');
  zero.forEach((c) => assert.ok(/^0\//.test(c.display), 'a real zero must print as 0/n'));
});

test('a cell that did not run has no rate at all, rather than a rate of 0', () => {
  const model = report.buildViewModel(table);
  model.heat.rows.forEach((row) => row.cells.forEach((c) => {
    if (c.state !== 'ran') assert.strictEqual(c.rate, null, c.arm + '/' + c.taskId);
  }));
});

/* -------------------------------------------------------------- effort panel */

test('the prediction band comes from the registration, not from the results', () => {
  const model = report.buildViewModel(table);
  const reg = model.effort.registration;
  assert.ok(reg.band, 'no predicted band');
  assert.deepStrictEqual(
    { low: reg.band.low, high: reg.band.high },
    {
      low: table.prereg_grading.h_effort.registration.predicted_reduction_pct.low,
      high: table.prereg_grading.h_effort.registration.predicted_reduction_pct.high,
    }
  );
  assert.ok(reg.file && /preregistrations/.test(reg.file), 'the band must name its registration file');
  assert.strictEqual(reg.publishEitherWay, true);
});

test('tasks outside the registered scope are shown but never graded', () => {
  const model = report.buildViewModel(table);
  const exploratory = model.effort.byTask.filter((r) => r.verdict === 'exploratory_not_graded');
  assert.ok(exploratory.length >= 1, 'the fixture must include out-of-scope task classes');
  exploratory.forEach((row) => assert.strictEqual(row.inScope, false));
  assert.strictEqual(model.effort.nExploratory, exploratory.length);
});

test('the panel keeps a refuted verdict rather than dropping it', () => {
  const model = report.buildViewModel(table);
  const verdicts = model.effort.byTask.map((r) => r.verdict);
  assert.ok(verdicts.indexOf('gate_parity_refuted') !== -1,
    'expected the fixture to exercise a refutation; got ' + verdicts.join(', '));
  assert.ok(verdicts.indexOf('within_predicted_band') !== -1);
  assert.ok(verdicts.indexOf('below_predicted_band') !== -1);
  assert.ok(verdicts.indexOf('above_predicted_band') !== -1);
});

test('each effort row carries both arms with their own scope lines', () => {
  const model = report.buildViewModel(table);
  model.effort.byTask.forEach((row) => {
    assert.strictEqual(row.arms.length, 2, row.taskId + ' should pair exactly two arms');
    row.arms.forEach((arm) => {
      assert.ok(arm.scopeLine, 'no scope line for ' + row.taskId + '/' + arm.arm);
      if (arm.ecst === null) assert.notStrictEqual(arm.status, 'derived');
    });
  });
});

/* ------------------------------------------------------------- routing view */

test('the escalation probe reports the gate result and the branch separately', () => {
  const model = report.buildViewModel(table);
  const esc = model.routing.escalation;
  assert.ok(esc, 'no escalation panel');
  assert.ok(['failed', 'passed', 'mixed', 'no_data'].indexOf(esc.economicalGate) !== -1);
  assert.ok(['observed', 'not_observed', 'no_data'].indexOf(esc.branch) !== -1);
  assert.ok(esc.outcomeBasis, 'an outcome must state what it rests on');
  assert.strictEqual(esc.registration.publishEitherWay, true);
});

test('every traced run shows where it intended to route and where it finished', () => {
  const model = report.buildViewModel(table);
  const esc = model.routing.escalation;
  assert.ok(esc.trace.length >= 1);
  esc.trace.forEach((run) => {
    assert.ok(run.intention, 'run ' + run.index + ' has no routing intention');
    assert.ok(run.completed, 'run ' + run.index + ' has no completed route');
    assert.ok(run.legs.length >= 1);
    if (run.fired) {
      assert.ok(run.legs.length >= 2,
        'an escalated run bills at least two legs; run ' + run.index + ' billed ' + run.legs.length);
    }
  });
});

test('a two-leg bill is itemised and its total is marked as a floor', () => {
  const model = report.buildViewModel(table);
  const bill = model.routing.bills.find((b) => b.rows.some((r) => !r.cost.available));
  assert.ok(bill.rows.length >= 2);
  assert.ok(bill.total.isFloor || bill.total.value === null,
    'a bill with an unpriced leg must not present a complete total');
  assert.ok(bill.scopeLine, 'the bill card must carry a scope line');
  assert.ok(bill.tier, 'the bill card must carry a confidence tier');
});

test('an unpriced leg reports no usage rather than the other leg’s usage', () => {
  const model = report.buildViewModel(table);
  const bill = model.routing.bills.find((b) => b.rows.some((r) => !r.cost.available));
  const dark = bill.rows.find((r) => !r.cost.available);
  const reported = dark.usage.filter((u) => u.value !== null);
  assert.strictEqual(reported.length, 0,
    'a leg the harness cannot see must not report token totals: ' +
    reported.map((u) => u.tokenClass).join(', '));
  dark.usage.forEach((u) => assert.ok(u.reason, u.tokenClass + ' is unavailable with no reason given'));
});

/* ---------------------------------------------------------------- coverage */

test('a registered arm that never ran is listed, not dropped', () => {
  const model = report.buildViewModel(table);
  const missing = model.coverage.rows.filter((r) => r.missing.length);
  assert.ok(missing.length >= 1, 'the fixture must exercise the missing-cell path');
  assert.strictEqual(model.coverage.complete, false);
  assert.ok(model.coverage.source, 'coverage must name where the registered matrix came from');
});

/* ------------------------------------------------------------ source safety */

test('only same-origin relative paths are loadable', () => {
  assert.strictEqual(report.resolveSource('?src=data/table.json', null).src, 'data/table.json');
  assert.strictEqual(report.resolveSource('?src=https://example.com/t.json', null).src, null);
  assert.strictEqual(report.resolveSource('?src=//example.com/t.json', null).src, null);
  assert.strictEqual(report.resolveSource('?src=../../etc/passwd', null).src, null);
  assert.strictEqual(report.resolveSource('', null).src, 'assets/data/decision-table.json');
  assert.strictEqual(report.resolveSource('', null).origin, 'default');
});

test('the mount point can override the default source', () => {
  const fakeMount = { getAttribute: (name) => (name === 'data-src' ? 'decision-table-SYNTHETIC.json' : null) };
  const resolved = report.resolveSource('', fakeMount);
  assert.strictEqual(resolved.src, 'decision-table-SYNTHETIC.json');
  assert.strictEqual(resolved.origin, 'attribute');
});

/* ------------------------------------------------------------------ axis */

test('axis ticks are ascending, start at zero and cover the data', () => {
  [0.05, 0.4, 1.7, 23, 940].forEach((max) => {
    const t = report.ticks(max);
    assert.strictEqual(t[0], 0);
    assert.ok(t[t.length - 1] >= max, 'ticks do not cover ' + max);
    assert.ok(t.length <= 8, 'too many gridlines for ' + max);
    t.forEach((v, i) => { if (i) assert.ok(v > t[i - 1], 'ticks not ascending'); });
  });
  assert.deepStrictEqual(report.ticks(0), [0]);
});

/* -------------------------------------------------------------- empty state */

test('a missing table yields an empty state, not a half-drawn page', () => {
  assert.strictEqual(report.buildViewModel(null).ok, false);
  assert.strictEqual(report.buildViewModel(undefined).ok, false);
  const empty = report.buildViewModel({});
  assert.strictEqual(empty.ok, true);
  assert.deepStrictEqual(empty.classes, []);
  assert.strictEqual(empty.effort, null);
  assert.strictEqual(empty.coverage, null);
});

/* -------------------------------------------------------------------- run */

let failed = 0;
tests.forEach(([name, fn]) => {
  try {
    fn();
    process.stdout.write('  ok   ' + name + '\n');
  } catch (err) {
    failed += 1;
    process.stdout.write('  FAIL ' + name + '\n       ' + err.message + '\n');
  }
});
process.stdout.write((failed ? 'FAILED ' + failed + ' of ' : 'passed all ') + tests.length + ' view-model tests\n');
process.exit(failed ? 1 : 0);
