# Screening report

This page is a **renderer, not a report**. It contains no figures of its own: it draws
whatever `decision-table.json` it is pointed at, and it ships pointed at nothing. What
you see below until a table is supplied is the empty state — that is correct, not broken.

!!! warning "This page is gated"

    Pointing this renderer at a real dataset is gated by **CP-FINDINGS**, and publishing
    a build of this site that contains one is gated by **CP-PUBLISH**. No screening
    figure may appear here, in the docs, or on the site before those checkpoints. The
    local data directory it reads from is gitignored, so a table can be reviewed on a
    workstation without any number entering the repository.

## What it draws

Each view exists to keep a specific mistake out of the room:

| View | What it shows | The mistake it prevents |
|---|---|---|
| **Decision cards, by task class** | Cost per accepted outcome, one bar per arm, grouped by task and banded by comparison type | A single leaderboard. Three different comparison types cannot share a ranking (SPEC §2.1), so the page never builds one. |
| **Acceptance matrix** | Share of runs that cleared the pre-registered gate, arm × task | Confusing "did not run" with "ran and failed". Three empty states are drawn differently. |
| **Effort panel** | The registered high-vs-medium prediction, with its predicted band drawn behind the observed result | Re-fitting a prediction after seeing the data. The band is drawn from the registration file, not from the results. |
| **Routing** | The escalation probe's per-run trace, and every multi-leg bill itemised leg by leg | Reading a delegation total as a model comparison, and quietly completing a bill whose second leg is unpriced. |
| **Coverage** | Registered arms versus arms that actually ran | A silently absent cell reading as a cell that was never planned. |

Every figure carries its **n**. Every card carries its **scope line** and **confidence
tier**. A measure the product does not expose renders as `unavailable` with the reason
attached — never as `0`, never as a blank cell, and never estimated from a neighbouring
value.

## Scoping

Screening is hypothesis-seeking positioning evidence (SPEC §5). A result on one task is a
signal about **that task under the conditions in its scope line** — not a workload-class
claim and not a product claim. Promoting anything here to a class-level statement requires
a second, materially different task from the same class (SPEC §5.2). Nothing rendered here
is independently publishable.

The comparison bands are not tiers of one ranking. A within-product tier comparison, a
within-product routing-policy comparison and a hybrid-workflow figure answer different
questions; the renderer separates them with a labelled gap and never sorts across them.

## Pointing it at a table

```bash
# 1. produce a decision table from a batch of runs
.venv/bin/python -m harness.telemetry.summarize results/<batch-dir> --out-dir report/<batchN>

# 2. put it where the page looks (this directory is gitignored)
mkdir -p docs/assets/data
cp report/<batchN>/decision-table.json docs/assets/data/decision-table.json

# 3. serve the docs locally
mkdocs serve
```

The renderer resolves its source in this order: a `?src=` query parameter, the mount
point's `data-src` attribute, then `assets/data/decision-table.json`. Only same-origin
relative paths are accepted — a crafted link cannot make this page fetch from an external
service, and it uses no browser storage.

To review the rendering itself without any real data, open the synthetic preview:

```bash
python3 -m http.server -d . 8000
# then: http://localhost:8000/tests/fixtures/decision-report-preview-SYNTHETIC.html
```

That preview is driven by `tests/fixtures/decision-table-SYNTHETIC.json`, whose every
number is fabricated by a generator script to exercise the renderer's paths — including
the unavailable-cost, no-accepted-outcome, registered-but-not-run and unpriced-leg cases.
It is labelled as synthetic in the file, in the filename, and in a banner across the top
of the page, and it is not a measurement of anything.

<div id="decision-report"></div>
