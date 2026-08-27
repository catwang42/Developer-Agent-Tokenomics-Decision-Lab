# Transfer-probe strategy specs

Three routing strategies transplanted from an external benchmark into this lab,
frozen as data. Nothing here is executable: `harness/adapters/transfer_r9.py`,
`transfer_r6.py` and `transfer_r10.py` read these YAML files and are driven by
them alone.

**Prereg (authoritative):** `manifest/preregistrations/2026-08-27-transfer-probe.md`.
Where this directory and the prereg disagree, the prereg wins.

| File | What it is |
|---|---|
| `r9-spec.yaml` | escalate-on-evidence — the gate READS the failure |
| `r6-spec.yaml` | opus-after-ladder — the gate COUNTS the failures |
| `r10-spec.yaml` | opus-fresh-solve — the frontier turn DISCARDS the failure |
| `calibration-slice.yaml` | the 5 pinned BigCodeBench-Hard tasks and the automatic gate |
| `source/` | byte-exact extracts from the source repo; see `source/NOTICE.md` |

## Why three arms and not one

They differ in exactly one dimension: how much of the cheap model's output the
expensive turn is allowed to trust. r9 reads it, r6 counts it, r10 throws it
away. r6 and r10 are otherwise byte-identical in configuration — one key,
`frontier_mode`, separates them — so r10 is a control, not a third contender.

The registered prediction is that this gradient orders how well each arm
survives a grader the cheap model's output cannot satisfy. W6's sealed gate
scores by line proximity (±3 lines), and a review that passes every public
check can still be rejected. An arm that repairs such a report inherits its
error; an arm that discards it does not.

> "Fabricated" in this instrument means a report falling outside the ±3-line
> window. It does not mean a false claim, and must not be reported as one.
> — prereg

## What is frozen and what is a judgment call

Frozen: the gate logic, the rung count, the frontier budget, the prompts, and
the digest treatment — each pinned by sha256 against a `source/*.py.txt`
extract, and re-hashed by `tests/test_transfer_specs.py`.

Not frozen, and listed as numbered judgment calls in every spec: the rung
*identity* (J-2 — the lab runs three Product-A economical rungs, not the
source's three Gemini tiers), the evidence *source* (J-3 — failing public check
ids stand in for typed test identities), and the repair *role text* (J-4 — the
source's wording names unit tests and demands a Python function, which two of
the three probe tasks do not have).

Read the `judgment_calls:` block before reading any result. The specs list
seven to ten each; a spec listing none would mean the transplant was not
examined, not that it was clean.

## Rules for this directory

- Model references are placeholders (`STRONG_MODEL_A`, `ECONOMICAL_MODEL_A`) and
  resolve only through `manifest/delivery-manifest.yaml`. No model id and no
  price appears in a spec file.
- Files under `source/` are evidence. Do not edit, reformat or reflow them; a
  change there breaks the sha256 pins and the tests, which is the intended
  behaviour.
- Every published figure in these files is read from the source's results file
  at the pinned sha. Figures computed here from those numbers are prefixed
  `derived_` and name the input they were computed from. No number in this
  directory describes a run this lab has performed, because none has.

## Open blocker before launch

`calibration-slice.yaml` → `cost_criterion_blocker`. The prereg's ±30% cost
criterion compares a lab-ladder bill against a source-ladder bill; re-pricing
the source's own published token volumes at this lab's rate card already puts
every arm between 1.5× and 3.1× the published cost. The criterion is
unpassable on the lab ladder before anything is spent. Three options are
written up there. **The decision is the human's and has not been taken.** The
runner implements the criterion exactly as worded and exits non-zero.
