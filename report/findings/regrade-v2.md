# Offline regrade-v2 sweep — what it changed

**STATUS: AUTHORITATIVE** for the regrade-v2 pass over the screening datasets.
Generated 2026-08-21T04:03:57Z from the records the sweep wrote; harness 4796df8.
Zero model spend: both gates were re-run in `--network=none` containers against
the archived `agent-solution.diff`. No sealed file is read here.

## How to read a row

`changed by this pass` compares v2 to the NEWEST prior verdict — for a run the
v1 pass already amended, that is v1's verdict, not the original one.
`changed vs original` is what the individual `regrade-v2-summary.json` records
carry, and it double-counts flips v1 had already found. Both are shown so the
two never look like a contradiction.

## Counts

- runs in scope: **145**
- re-graded: **145** (111 graded, 34 refused as truncated)
- not reached by the sweep: **0**
- verdicts changed **by this pass**: **5**
- verdicts different from the original archive: 22 (of which 17 were already found by the v1 regrade)
- public checks cleared (grader artifacts): **28**
- public checks newly failing (regressions): **0** across 0 run(s)

## Gate images used

Every tag carries the gate-content digest introduced in PR #27, so none of
these could have been served from a pre-fix cache:

- `lab-subject/pilot-realworld-draft-articles:30b68e1e8814-a6dff3bb`
- `lab-subject/w1-realworld-mapper-tests:30b68e1e8814-0708bd85`
- `lab-subject/w1b-zarr-block-mask-properties:b9d396460da3-d81ff362`
- `lab-subject/w3-sqlfluff-segment-method-migration:7700446fdb42-4e14b6fd`
- `lab-subject/w4-realworld-missing-user-id:88b258ce54aa-9b708a7c`
- `lab-subject/w4b-zarr-consolidated-order:a994a4fc972f-5f2f874b`
- `lab-subject/w6-hono-router-review:3feb3551d46d-5c838042`

## Per cell

| dataset | task | arm | rep | verdict ladder | changed by this pass | changed vs original | gate image | public checks |
|---|---|---|---|---|---|---|---|---|
| screening-batch1 | pilot-realworld-draft-articles | C2 | 1 | accepted → accepted (v2) | no | no | lab-subject/pilot-realworld-draft-articles:30b68e1e8814-a6dff3bb | — |
| screening-batch1 | pilot-realworld-draft-articles | C2 | 2 | accepted → accepted (v2) | no | no | lab-subject/pilot-realworld-draft-articles:30b68e1e8814-a6dff3bb | — |
| screening-batch1 | pilot-realworld-draft-articles | C2 | 3 | accepted → accepted (v2) | no | no | lab-subject/pilot-realworld-draft-articles:30b68e1e8814-a6dff3bb | — |
| screening-batch1 | pilot-realworld-draft-articles | C3-med | 1 | accepted → accepted (v2) | no | no | lab-subject/pilot-realworld-draft-articles:30b68e1e8814-a6dff3bb | — |
| screening-batch1 | pilot-realworld-draft-articles | C3-med | 2 | accepted → accepted (v2) | no | no | lab-subject/pilot-realworld-draft-articles:30b68e1e8814-a6dff3bb | — |
| screening-batch1 | pilot-realworld-draft-articles | C3-med | 3 | accepted → accepted (v2) | no | no | lab-subject/pilot-realworld-draft-articles:30b68e1e8814-a6dff3bb | — |
| screening-batch1 | pilot-realworld-draft-articles | C3-prev | 1 | accepted → accepted (v2) | no | no | lab-subject/pilot-realworld-draft-articles:30b68e1e8814-a6dff3bb | — |
| screening-batch1 | pilot-realworld-draft-articles | C3-prev | 2 | accepted → accepted (v2) | no | no | lab-subject/pilot-realworld-draft-articles:30b68e1e8814-a6dff3bb | — |
| screening-batch1 | pilot-realworld-draft-articles | C3 | 1 | accepted → accepted (v2) | no | no | lab-subject/pilot-realworld-draft-articles:30b68e1e8814-a6dff3bb | — |
| screening-batch1 | pilot-realworld-draft-articles | C3 | 2 | accepted → accepted (v2) | no | no | lab-subject/pilot-realworld-draft-articles:30b68e1e8814-a6dff3bb | — |
| screening-batch1 | pilot-realworld-draft-articles | C5 | 1 | accepted → accepted (v2) | no | no | lab-subject/pilot-realworld-draft-articles:30b68e1e8814-a6dff3bb | — |
| screening-batch1 | pilot-realworld-draft-articles | C5 | 2 | accepted → accepted (v2) | no | no | lab-subject/pilot-realworld-draft-articles:30b68e1e8814-a6dff3bb | — |
| screening-batch1 | pilot-realworld-draft-articles | P0 | 1 | accepted → accepted (v2) | no | no | lab-subject/pilot-realworld-draft-articles:30b68e1e8814-a6dff3bb | — |
| screening-batch1 | pilot-realworld-draft-articles | P0 | 2 | accepted → accepted (v2) | no | no | lab-subject/pilot-realworld-draft-articles:30b68e1e8814-a6dff3bb | — |
| screening-batch1 | pilot-realworld-draft-articles | P0 | 3 | accepted → accepted (v2) | no | no | lab-subject/pilot-realworld-draft-articles:30b68e1e8814-a6dff3bb | — |
| screening-batch1 | w1-realworld-mapper-tests | C2 | 1 | rejected → accepted (v1) → accepted (v2) | no | yes | lab-subject/w1-realworld-mapper-tests:30b68e1e8814-0708bd85 | hidden fail → pass |
| screening-batch1 | w1-realworld-mapper-tests | C2 | 2 | rejected → accepted (v1) → accepted (v2) | no | yes | lab-subject/w1-realworld-mapper-tests:30b68e1e8814-0708bd85 | hidden fail → pass |
| screening-batch1 | w1-realworld-mapper-tests | C2 | 3 | rejected → accepted (v1) → accepted (v2) | no | yes | lab-subject/w1-realworld-mapper-tests:30b68e1e8814-0708bd85 | hidden fail → pass |
| screening-batch1 | w1-realworld-mapper-tests | C3-med | 1 | rejected → accepted (v1) → accepted (v2) | no | yes | lab-subject/w1-realworld-mapper-tests:30b68e1e8814-0708bd85 | hidden fail → pass |
| screening-batch1 | w1-realworld-mapper-tests | C3-med | 2 | rejected → accepted (v1) → accepted (v2) | no | yes | lab-subject/w1-realworld-mapper-tests:30b68e1e8814-0708bd85 | hidden fail → pass |
| screening-batch1 | w1-realworld-mapper-tests | C3-med | 3 | rejected → accepted (v1) → accepted (v2) | no | yes | lab-subject/w1-realworld-mapper-tests:30b68e1e8814-0708bd85 | hidden fail → pass |
| screening-batch1 | w1-realworld-mapper-tests | C3-prev | 1 | rejected → accepted (v1) → accepted (v2) | no | yes | lab-subject/w1-realworld-mapper-tests:30b68e1e8814-0708bd85 | hidden fail → pass |
| screening-batch1 | w1-realworld-mapper-tests | C3-prev | 2 | rejected → accepted (v1) → accepted (v2) | no | yes | lab-subject/w1-realworld-mapper-tests:30b68e1e8814-0708bd85 | hidden fail → pass |
| screening-batch1 | w1-realworld-mapper-tests | C3-prev | 3 | rejected → accepted (v1) → accepted (v2) | no | yes | lab-subject/w1-realworld-mapper-tests:30b68e1e8814-0708bd85 | hidden fail → pass |
| screening-batch1 | w1-realworld-mapper-tests | C3 | 1 | rejected → accepted (v1) → accepted (v2) | no | yes | lab-subject/w1-realworld-mapper-tests:30b68e1e8814-0708bd85 | hidden fail → pass |
| screening-batch1 | w1-realworld-mapper-tests | C3 | 2 | rejected → accepted (v1) → accepted (v2) | no | yes | lab-subject/w1-realworld-mapper-tests:30b68e1e8814-0708bd85 | hidden fail → pass |
| screening-batch1 | w1-realworld-mapper-tests | C3 | 3 | rejected → accepted (v1) → accepted (v2) | no | yes | lab-subject/w1-realworld-mapper-tests:30b68e1e8814-0708bd85 | hidden fail → pass |
| screening-batch1 | w1-realworld-mapper-tests | C5 | 1 | REFUSED | — | — | — | truncated: no completed agent product |
| screening-batch1 | w1-realworld-mapper-tests | C5 | 2 | rejected → accepted (v1) → accepted (v2) | no | yes | lab-subject/w1-realworld-mapper-tests:30b68e1e8814-0708bd85 | hidden fail → pass |
| screening-batch1 | w1-realworld-mapper-tests | C5 | 3 | rejected → accepted (v1) → accepted (v2) | no | yes | lab-subject/w1-realworld-mapper-tests:30b68e1e8814-0708bd85 | hidden fail → pass |
| screening-batch1 | w1-realworld-mapper-tests | P0 | 1 | rejected → accepted (v1) → accepted (v2) | no | yes | lab-subject/w1-realworld-mapper-tests:30b68e1e8814-0708bd85 | hidden fail → pass |
| screening-batch1 | w1-realworld-mapper-tests | P0 | 2 | rejected → accepted (v1) → accepted (v2) | no | yes | lab-subject/w1-realworld-mapper-tests:30b68e1e8814-0708bd85 | hidden fail → pass |
| screening-batch1 | w1-realworld-mapper-tests | P0 | 3 | rejected → accepted (v1) → accepted (v2) | no | yes | lab-subject/w1-realworld-mapper-tests:30b68e1e8814-0708bd85 | hidden fail → pass |
| screening-batch1 | w1b-zarr-block-mask-properties | C2 | 1 | rejected → rejected (v1) → rejected (v2) | no | no | lab-subject/w1b-zarr-block-mask-properties:b9d396460da3-d81ff362 | genuine failure, public: T2-suite-green, T3-coverage, T4-tests-pass; hidden fail → pass |
| screening-batch1 | w1b-zarr-block-mask-properties | C2 | 2 | rejected → rejected (v1) → rejected (v2) | no | no | lab-subject/w1b-zarr-block-mask-properties:b9d396460da3-d81ff362 | genuine failure, public: T2-suite-green, T3-coverage, T4-tests-pass; hidden fail → pass |
| screening-batch1 | w1b-zarr-block-mask-properties | C2 | 3 | rejected → rejected (v1) → rejected (v2) | no | no | lab-subject/w1b-zarr-block-mask-properties:b9d396460da3-d81ff362 | genuine failure, public: T2-suite-green, T3-coverage, T4-tests-pass; hidden fail → pass |
| screening-batch1 | w1b-zarr-block-mask-properties | C3-med | 1 | rejected → rejected (v1) → rejected (v2) | no | no | lab-subject/w1b-zarr-block-mask-properties:b9d396460da3-d81ff362 | genuine failure, public: T2-suite-green, T3-coverage, T4-tests-pass; hidden fail → pass |
| screening-batch1 | w1b-zarr-block-mask-properties | C3-med | 2 | rejected → rejected (v1) → rejected (v2) | no | no | lab-subject/w1b-zarr-block-mask-properties:b9d396460da3-d81ff362 | genuine failure, public: T2-suite-green, T3-coverage, T4-tests-pass; hidden fail → pass |
| screening-batch1 | w1b-zarr-block-mask-properties | C3-med | 3 | rejected → rejected (v1) → rejected (v2) | no | no | lab-subject/w1b-zarr-block-mask-properties:b9d396460da3-d81ff362 | genuine failure, public: T2-suite-green, T3-coverage, T4-tests-pass; hidden fail → pass |
| screening-batch1 | w1b-zarr-block-mask-properties | C3-prev | 1 | rejected → rejected (v1) → rejected (v2) | no | no | lab-subject/w1b-zarr-block-mask-properties:b9d396460da3-d81ff362 | genuine failure, public: T2-suite-green, T3-coverage, T4-tests-pass; hidden fail → pass |
| screening-batch1 | w1b-zarr-block-mask-properties | C3-prev | 2 | rejected → rejected (v1) → rejected (v2) | no | no | lab-subject/w1b-zarr-block-mask-properties:b9d396460da3-d81ff362 | genuine failure, public: T2-suite-green, T3-coverage, T4-tests-pass; hidden fail → pass |
| screening-batch1 | w1b-zarr-block-mask-properties | C3-prev | 3 | rejected → rejected (v1) → rejected (v2) | no | no | lab-subject/w1b-zarr-block-mask-properties:b9d396460da3-d81ff362 | genuine failure, public: T2-suite-green, T3-coverage, T4-tests-pass; hidden fail → pass |
| screening-batch1 | w1b-zarr-block-mask-properties | C3 | 1 | rejected → rejected (v1) → rejected (v2) | no | no | lab-subject/w1b-zarr-block-mask-properties:b9d396460da3-d81ff362 | genuine failure, public: T2-suite-green, T3-coverage, T4-tests-pass; hidden fail → pass |
| screening-batch1 | w1b-zarr-block-mask-properties | C3 | 2 | rejected → rejected (v1) → rejected (v2) | no | no | lab-subject/w1b-zarr-block-mask-properties:b9d396460da3-d81ff362 | genuine failure, public: T2-suite-green, T3-coverage, T4-tests-pass; hidden fail → pass |
| screening-batch1 | w1b-zarr-block-mask-properties | C3 | 3 | rejected → rejected (v1) → rejected (v2) | no | no | lab-subject/w1b-zarr-block-mask-properties:b9d396460da3-d81ff362 | genuine failure, public: T2-suite-green, T3-coverage, T4-tests-pass; hidden fail → pass |
| screening-batch1 | w1b-zarr-block-mask-properties | C5 | 1 | rejected → rejected (v1) → rejected (v2) | no | no | lab-subject/w1b-zarr-block-mask-properties:b9d396460da3-d81ff362 | genuine failure, public: T2-suite-green, T3-coverage, T4-tests-pass; hidden fail → pass |
| screening-batch1 | w1b-zarr-block-mask-properties | C5 | 2 | rejected → rejected (v1) → rejected (v2) | no | no | lab-subject/w1b-zarr-block-mask-properties:b9d396460da3-d81ff362 | genuine failure, public: T2-suite-green, T3-coverage, T4-tests-pass; hidden fail → pass |
| screening-batch1 | w1b-zarr-block-mask-properties | C5 | 3 | rejected → rejected (v1) → rejected (v2) | no | no | lab-subject/w1b-zarr-block-mask-properties:b9d396460da3-d81ff362 | genuine failure, public: T2-suite-green, T3-coverage, T4-tests-pass; hidden fail → pass |
| screening-batch1 | w1b-zarr-block-mask-properties | P0 | 1 | REFUSED | — | — | — | truncated: no completed agent product |
| screening-batch1 | w1b-zarr-block-mask-properties | P0 | 2 | rejected → rejected (v1) → rejected (v2) | no | no | lab-subject/w1b-zarr-block-mask-properties:b9d396460da3-d81ff362 | genuine failure, public: T2-suite-green, T3-coverage, T4-tests-pass; hidden fail → pass |
| screening-batch1 | w1b-zarr-block-mask-properties | P0 | 3 | rejected → rejected (v1) → rejected (v2) | no | no | lab-subject/w1b-zarr-block-mask-properties:b9d396460da3-d81ff362 | genuine failure, public: T2-suite-green, T3-coverage, T4-tests-pass; hidden fail → pass |
| screening-batch1 | w3-sqlfluff-segment-method-migration | C2 | 1 | REFUSED | — | — | — | truncated: no completed agent product |
| screening-batch1 | w3-sqlfluff-segment-method-migration | C2 | 2 | REFUSED | — | — | — | truncated: no completed agent product |
| screening-batch1 | w3-sqlfluff-segment-method-migration | C2 | 3 | REFUSED | — | — | — | truncated: no completed agent product |
| screening-batch1 | w3-sqlfluff-segment-method-migration | C3-med | 1 | rejected → rejected (v2) | no | no | lab-subject/w3-sqlfluff-segment-method-migration:7700446fdb42-4e14b6fd | genuine failure, public: P1-public-test, P2-regression |
| screening-batch1 | w3-sqlfluff-segment-method-migration | C3-med | 2 | rejected → rejected (v2) | no | no | lab-subject/w3-sqlfluff-segment-method-migration:7700446fdb42-4e14b6fd | genuine failure, public: P1-public-test, P2-regression |
| screening-batch1 | w3-sqlfluff-segment-method-migration | C3-med | 3 | rejected → rejected (v2) | no | no | lab-subject/w3-sqlfluff-segment-method-migration:7700446fdb42-4e14b6fd | genuine failure, public: P1-public-test, P2-regression |
| screening-batch1 | w3-sqlfluff-segment-method-migration | C3-prev | 1 | rejected → rejected (v2) | no | no | lab-subject/w3-sqlfluff-segment-method-migration:7700446fdb42-4e14b6fd | genuine failure, public: P1-public-test, P2-regression |
| screening-batch1 | w3-sqlfluff-segment-method-migration | C3-prev | 2 | rejected → rejected (v2) | no | no | lab-subject/w3-sqlfluff-segment-method-migration:7700446fdb42-4e14b6fd | genuine failure, public: P1-public-test, P2-regression |
| screening-batch1 | w3-sqlfluff-segment-method-migration | C3-prev | 3 | rejected → rejected (v2) | no | no | lab-subject/w3-sqlfluff-segment-method-migration:7700446fdb42-4e14b6fd | genuine failure, public: P1-public-test, P2-regression |
| screening-batch1 | w3-sqlfluff-segment-method-migration | C3 | 1 | rejected → rejected (v2) | no | no | lab-subject/w3-sqlfluff-segment-method-migration:7700446fdb42-4e14b6fd | genuine failure, public: P1-public-test, P2-regression |
| screening-batch1 | w3-sqlfluff-segment-method-migration | C3 | 2 | rejected → rejected (v2) | no | no | lab-subject/w3-sqlfluff-segment-method-migration:7700446fdb42-4e14b6fd | genuine failure, public: P1-public-test, P2-regression |
| screening-batch1 | w3-sqlfluff-segment-method-migration | C3 | 3 | rejected → rejected (v2) | no | no | lab-subject/w3-sqlfluff-segment-method-migration:7700446fdb42-4e14b6fd | genuine failure, public: P1-public-test, P2-regression |
| screening-batch1 | w3-sqlfluff-segment-method-migration | C5 | 1 | REFUSED | — | — | — | truncated: no completed agent product |
| screening-batch1 | w3-sqlfluff-segment-method-migration | C5 | 2 | REFUSED | — | — | — | truncated: no completed agent product |
| screening-batch1 | w3-sqlfluff-segment-method-migration | C5 | 3 | REFUSED | — | — | — | truncated: no completed agent product |
| screening-batch1 | w3-sqlfluff-segment-method-migration | P0 | 1 | REFUSED | — | — | — | truncated: no completed agent product |
| screening-batch1 | w3-sqlfluff-segment-method-migration | P0 | 2 | REFUSED | — | — | — | truncated: no completed agent product |
| screening-batch1 | w3-sqlfluff-segment-method-migration | P0 | 3 | REFUSED | — | — | — | truncated: no completed agent product |
| screening-batch1 | w3-sqlfluff-segment-method-migration | P1 | 1 | REFUSED | — | — | — | truncated: no completed agent product |
| screening-batch1 | w3-sqlfluff-segment-method-migration | P1 | 2 | REFUSED | — | — | — | truncated: no completed agent product |
| screening-batch1 | w3-sqlfluff-segment-method-migration | P1 | 3 | REFUSED | — | — | — | truncated: no completed agent product |
| screening-batch1 | w4-realworld-missing-user-id | C2 | 1 | accepted → accepted (v2) | no | no | lab-subject/w4-realworld-missing-user-id:88b258ce54aa-9b708a7c | — |
| screening-batch1 | w4-realworld-missing-user-id | C2 | 2 | accepted → accepted (v2) | no | no | lab-subject/w4-realworld-missing-user-id:88b258ce54aa-9b708a7c | — |
| screening-batch1 | w4-realworld-missing-user-id | C2 | 3 | accepted → accepted (v2) | no | no | lab-subject/w4-realworld-missing-user-id:88b258ce54aa-9b708a7c | — |
| screening-batch1 | w4-realworld-missing-user-id | C3-med | 1 | accepted → accepted (v2) | no | no | lab-subject/w4-realworld-missing-user-id:88b258ce54aa-9b708a7c | — |
| screening-batch1 | w4-realworld-missing-user-id | C3-med | 2 | accepted → accepted (v2) | no | no | lab-subject/w4-realworld-missing-user-id:88b258ce54aa-9b708a7c | — |
| screening-batch1 | w4-realworld-missing-user-id | C3-med | 3 | accepted → accepted (v2) | no | no | lab-subject/w4-realworld-missing-user-id:88b258ce54aa-9b708a7c | — |
| screening-batch1 | w4-realworld-missing-user-id | C3-prev | 1 | rejected → rejected (v2) | no | no | lab-subject/w4-realworld-missing-user-id:88b258ce54aa-9b708a7c | genuine failure, public: P6-diff-scope |
| screening-batch1 | w4-realworld-missing-user-id | C3-prev | 2 | rejected → rejected (v2) | no | no | lab-subject/w4-realworld-missing-user-id:88b258ce54aa-9b708a7c | genuine failure, public: P6-diff-scope |
| screening-batch1 | w4-realworld-missing-user-id | C3-prev | 3 | rejected → rejected (v2) | no | no | lab-subject/w4-realworld-missing-user-id:88b258ce54aa-9b708a7c | genuine failure, public: P6-diff-scope |
| screening-batch1 | w4-realworld-missing-user-id | C3 | 1 | rejected → rejected (v2) | no | no | lab-subject/w4-realworld-missing-user-id:88b258ce54aa-9b708a7c | genuine failure, public: P6-diff-scope |
| screening-batch1 | w4-realworld-missing-user-id | C3 | 3 | accepted → accepted (v2) | no | no | lab-subject/w4-realworld-missing-user-id:88b258ce54aa-9b708a7c | — |
| screening-batch1 | w4-realworld-missing-user-id | C5 | 1 | accepted → accepted (v2) | no | no | lab-subject/w4-realworld-missing-user-id:88b258ce54aa-9b708a7c | — |
| screening-batch1 | w4-realworld-missing-user-id | C5 | 2 | rejected → rejected (v2) | no | no | lab-subject/w4-realworld-missing-user-id:88b258ce54aa-9b708a7c | genuine failure, public: P6-diff-scope |
| screening-batch1 | w4-realworld-missing-user-id | C5 | 3 | accepted → accepted (v2) | no | no | lab-subject/w4-realworld-missing-user-id:88b258ce54aa-9b708a7c | — |
| screening-batch1 | w4-realworld-missing-user-id | P0 | 1 | accepted → accepted (v2) | no | no | lab-subject/w4-realworld-missing-user-id:88b258ce54aa-9b708a7c | — |
| screening-batch1 | w4-realworld-missing-user-id | P0 | 2 | accepted → accepted (v2) | no | no | lab-subject/w4-realworld-missing-user-id:88b258ce54aa-9b708a7c | — |
| screening-batch1 | w4-realworld-missing-user-id | P0 | 3 | accepted → accepted (v2) | no | no | lab-subject/w4-realworld-missing-user-id:88b258ce54aa-9b708a7c | — |
| screening-batch1 | w4b-zarr-consolidated-order | C2 | 1 | rejected → rejected (v2) | no | no | lab-subject/w4b-zarr-consolidated-order:a994a4fc972f-5f2f874b | genuine failure, public: P1-public-test, P2-regression |
| screening-batch1 | w4b-zarr-consolidated-order | C2 | 2 | rejected → rejected (v2) | no | no | lab-subject/w4b-zarr-consolidated-order:a994a4fc972f-5f2f874b | genuine failure, public: P1-public-test, P2-regression |
| screening-batch1 | w4b-zarr-consolidated-order | C2 | 3 | rejected → rejected (v2) | no | no | lab-subject/w4b-zarr-consolidated-order:a994a4fc972f-5f2f874b | genuine failure, public: P1-public-test, P2-regression |
| screening-batch1 | w4b-zarr-consolidated-order | C3-med | 1 | rejected → rejected (v2) | no | no | lab-subject/w4b-zarr-consolidated-order:a994a4fc972f-5f2f874b | genuine failure, public: P1-public-test, P2-regression |
| screening-batch1 | w4b-zarr-consolidated-order | C3-med | 2 | rejected → rejected (v2) | no | no | lab-subject/w4b-zarr-consolidated-order:a994a4fc972f-5f2f874b | genuine failure, public: P1-public-test, P2-regression |
| screening-batch1 | w4b-zarr-consolidated-order | C3-med | 3 | rejected → rejected (v2) | no | no | lab-subject/w4b-zarr-consolidated-order:a994a4fc972f-5f2f874b | genuine failure, public: P1-public-test, P2-regression |
| screening-batch1 | w4b-zarr-consolidated-order | C3-prev | 1 | rejected → rejected (v2) | no | no | lab-subject/w4b-zarr-consolidated-order:a994a4fc972f-5f2f874b | genuine failure, public: P1-public-test, P2-regression, P6-diff-scope |
| screening-batch1 | w4b-zarr-consolidated-order | C3-prev | 2 | rejected → rejected (v2) | no | no | lab-subject/w4b-zarr-consolidated-order:a994a4fc972f-5f2f874b | genuine failure, public: P1-public-test, P2-regression, P6-diff-scope |
| screening-batch1 | w4b-zarr-consolidated-order | C3-prev | 3 | rejected → rejected (v2) | no | no | lab-subject/w4b-zarr-consolidated-order:a994a4fc972f-5f2f874b | genuine failure, public: P1-public-test, P2-regression, P6-diff-scope |
| screening-batch1 | w4b-zarr-consolidated-order | C3 | 1 | rejected → rejected (v2) | no | no | lab-subject/w4b-zarr-consolidated-order:a994a4fc972f-5f2f874b | genuine failure, public: P1-public-test, P2-regression |
| screening-batch1 | w4b-zarr-consolidated-order | C3 | 2 | rejected → rejected (v2) | no | no | lab-subject/w4b-zarr-consolidated-order:a994a4fc972f-5f2f874b | genuine failure, public: P1-public-test, P2-regression |
| screening-batch1 | w4b-zarr-consolidated-order | C3 | 3 | rejected → rejected (v2) | no | no | lab-subject/w4b-zarr-consolidated-order:a994a4fc972f-5f2f874b | genuine failure, public: P1-public-test, P2-regression |
| screening-batch1 | w4b-zarr-consolidated-order | C5 | 1 | REFUSED | — | — | — | truncated: no completed agent product |
| screening-batch1 | w4b-zarr-consolidated-order | C5 | 2 | REFUSED | — | — | — | truncated: no completed agent product |
| screening-batch1 | w4b-zarr-consolidated-order | C5 | 3 | rejected → rejected (v2) | no | no | lab-subject/w4b-zarr-consolidated-order:a994a4fc972f-5f2f874b | genuine failure, public: P1-public-test, P2-regression |
| screening-batch1 | w4b-zarr-consolidated-order | P0 | 1 | rejected → rejected (v2) | no | no | lab-subject/w4b-zarr-consolidated-order:a994a4fc972f-5f2f874b | genuine failure, public: P1-public-test, P2-regression |
| screening-batch1 | w4b-zarr-consolidated-order | P0 | 2 | rejected → rejected (v2) | no | no | lab-subject/w4b-zarr-consolidated-order:a994a4fc972f-5f2f874b | genuine failure, public: P1-public-test, P2-regression |
| screening-batch1 | w4b-zarr-consolidated-order | P0 | 3 | rejected → rejected (v2) | no | no | lab-subject/w4b-zarr-consolidated-order:a994a4fc972f-5f2f874b | genuine failure, public: P1-public-test, P2-regression |
| screening-batch1 | w6-hono-router-review | C2 | 1 | REFUSED | — | — | — | truncated: no completed agent product |
| screening-batch1 | w6-hono-router-review | C2 | 2 | REFUSED | — | — | — | truncated: no completed agent product |
| screening-batch1 | w6-hono-router-review | C2 | 3 | REFUSED | — | — | — | truncated: no completed agent product |
| screening-batch1 | w6-hono-router-review | C3-med | 1 | REFUSED | — | — | — | truncated: no completed agent product |
| screening-batch1 | w6-hono-router-review | C3-med | 2 | REFUSED | — | — | — | truncated: no completed agent product |
| screening-batch1 | w6-hono-router-review | C3-med | 3 | REFUSED | — | — | — | truncated: no completed agent product |
| screening-batch1 | w6-hono-router-review | C3-prev | 1 | REFUSED | — | — | — | truncated: no completed agent product |
| screening-batch1 | w6-hono-router-review | C3-prev | 2 | REFUSED | — | — | — | truncated: no completed agent product |
| screening-batch1 | w6-hono-router-review | C3-prev | 3 | REFUSED | — | — | — | truncated: no completed agent product |
| screening-batch1 | w6-hono-router-review | C3 | 1 | REFUSED | — | — | — | truncated: no completed agent product |
| screening-batch1 | w6-hono-router-review | C3 | 2 | REFUSED | — | — | — | truncated: no completed agent product |
| screening-batch1 | w6-hono-router-review | C3 | 3 | REFUSED | — | — | — | truncated: no completed agent product |
| screening-batch1 | w6-hono-router-review | P0 | 1 | REFUSED | — | — | — | truncated: no completed agent product |
| screening-batch1 | w6-hono-router-review | P0 | 2 | REFUSED | — | — | — | truncated: no completed agent product |
| screening-batch1 | w6-hono-router-review | P0 | 3 | REFUSED | — | — | — | truncated: no completed agent product |
| screening-batch1-makeup | w3-sqlfluff-segment-method-migration | C2 | 1 | rejected → rejected (v2) | no | no | lab-subject/w3-sqlfluff-segment-method-migration:7700446fdb42-4e14b6fd | genuine failure, public: P1-public-test, P2-regression |
| screening-batch1-makeup | w3-sqlfluff-segment-method-migration | C2 | 2 | rejected → rejected (v2) | no | no | lab-subject/w3-sqlfluff-segment-method-migration:7700446fdb42-4e14b6fd | genuine failure, public: P1-public-test, P2-regression |
| screening-batch1-makeup | w3-sqlfluff-segment-method-migration | C3 | 1 | rejected → rejected (v2) | no | no | lab-subject/w3-sqlfluff-segment-method-migration:7700446fdb42-4e14b6fd | genuine failure, public: P1-public-test, P2-regression |
| screening-batch1-makeup | w3-sqlfluff-segment-method-migration | C3 | 2 | rejected → rejected (v2) | no | no | lab-subject/w3-sqlfluff-segment-method-migration:7700446fdb42-4e14b6fd | genuine failure, public: P1-public-test, P2-regression |
| screening-batch1-makeup | w3-sqlfluff-segment-method-migration | P0 | 1 | REFUSED | — | — | — | truncated: no completed agent product |
| screening-batch1-makeup | w3-sqlfluff-segment-method-migration | P0 | 2 | rejected → rejected (v2) | no | no | lab-subject/w3-sqlfluff-segment-method-migration:7700446fdb42-4e14b6fd | genuine failure, public: P1-public-test, P2-regression |
| screening-batch1-makeup | w3-sqlfluff-segment-method-migration | P1 | 1 | REFUSED | — | — | — | truncated: no completed agent product |
| screening-batch1-makeup | w3-sqlfluff-segment-method-migration | P1 | 2 | rejected → rejected (v2) | no | no | lab-subject/w3-sqlfluff-segment-method-migration:7700446fdb42-4e14b6fd | genuine failure, public: P1-public-test, P2-regression |
| screening-batch1-makeup-w6 | w6-hono-router-review | C2 | 1 | rejected → rejected (v2) | no | no | lab-subject/w6-hono-router-review:3feb3551d46d-5c838042 | artifact flip, public: P5-no-leakage, P6-diff-scope |
| screening-batch1-makeup-w6 | w6-hono-router-review | C2 | 2 | REFUSED | — | — | — | truncated: no completed agent product |
| screening-batch1-makeup-w6 | w6-hono-router-review | C2 | 3 | rejected → accepted (v2) | yes | yes | lab-subject/w6-hono-router-review:3feb3551d46d-5c838042 | artifact flip, public: P5-no-leakage, P6-diff-scope |
| screening-batch1-makeup-w6 | w6-hono-router-review | C3-med | 1 | rejected → rejected (v2) | no | no | lab-subject/w6-hono-router-review:3feb3551d46d-5c838042 | artifact flip, public: P5-no-leakage, P6-diff-scope |
| screening-batch1-makeup-w6 | w6-hono-router-review | C3-med | 2 | rejected → accepted (v2) | yes | yes | lab-subject/w6-hono-router-review:3feb3551d46d-5c838042 | artifact flip, public: P5-no-leakage, P6-diff-scope |
| screening-batch1-makeup-w6 | w6-hono-router-review | C3-med | 3 | rejected → rejected (v2) | no | no | lab-subject/w6-hono-router-review:3feb3551d46d-5c838042 | artifact flip, public: P5-no-leakage, P6-diff-scope |
| screening-batch1-makeup-w6 | w6-hono-router-review | C3-prev | 1 | rejected → rejected (v2) | no | no | lab-subject/w6-hono-router-review:3feb3551d46d-5c838042 | artifact flip, public: P5-no-leakage, P6-diff-scope |
| screening-batch1-makeup-w6 | w6-hono-router-review | C3-prev | 2 | rejected → rejected (v2) | no | no | lab-subject/w6-hono-router-review:3feb3551d46d-5c838042 | artifact flip, public: P5-no-leakage, P6-diff-scope |
| screening-batch1-makeup-w6 | w6-hono-router-review | C3-prev | 3 | rejected → rejected (v2) | no | no | lab-subject/w6-hono-router-review:3feb3551d46d-5c838042 | artifact flip, public: P5-no-leakage, P6-diff-scope |
| screening-batch1-makeup-w6 | w6-hono-router-review | C3 | 1 | rejected → rejected (v2) | no | no | lab-subject/w6-hono-router-review:3feb3551d46d-5c838042 | artifact flip, public: P5-no-leakage, P6-diff-scope |
| screening-batch1-makeup-w6 | w6-hono-router-review | C3 | 2 | rejected → rejected (v2) | no | no | lab-subject/w6-hono-router-review:3feb3551d46d-5c838042 | artifact flip, public: P5-no-leakage, P6-diff-scope |
| screening-batch1-makeup-w6 | w6-hono-router-review | C3 | 3 | rejected → rejected (v2) | no | no | lab-subject/w6-hono-router-review:3feb3551d46d-5c838042 | artifact flip, public: P5-no-leakage, P6-diff-scope |
| screening-batch1-makeup-w6 | w6-hono-router-review | P0 | 1 | rejected → accepted (v2) | yes | yes | lab-subject/w6-hono-router-review:3feb3551d46d-5c838042 | artifact flip, public: P5-no-leakage, P6-diff-scope |
| screening-batch1-makeup-w6 | w6-hono-router-review | P0 | 2 | rejected → accepted (v2) | yes | yes | lab-subject/w6-hono-router-review:3feb3551d46d-5c838042 | artifact flip, public: P5-no-leakage, P6-diff-scope |
| screening-batch1-makeup-w6 | w6-hono-router-review | P0 | 3 | rejected → accepted (v2) | yes | yes | lab-subject/w6-hono-router-review:3feb3551d46d-5c838042 | artifact flip, public: P5-no-leakage, P6-diff-scope |
