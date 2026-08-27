# Stopwatch review — human review cost inputs

Reviewer: Catherine (senior engineer, familiar with the codebases at task level).
Method: blind. Candidates labelled a–e; model, arm and gate verdict unknown at
review time. Key opened only after all five decisions were recorded.
Rate applied: 80 USD/hour — "declared here as an
assumption".
Each artifact reviewed in one sitting, timer running, no fixing, no research
beyond what a reviewer would normally do.

## Decisions

| Candidate | Minutes | Decision | Confidence (1-5) | Defects found | Notes |
|---|---|---|---|---|---|
| a | 33 | request-changes | 5 | Deprecated alias wrappers hard-code ANSI dispatch, breaking behavior parity for non-ANSI dialects such as BigQuery. | FromExpressionElementSegment.get_eventual_alias(), JoinClauseSegment.get_eventual_aliases(), and FromClauseSegment.get_eventual_aliases() delegate using _reference_dialect_name = "ansi". That means existing callers using these deprecated methods on BigQuery paths can bypass BigQuery-specific reference parsing, including hyphenated/multipart table references. This violates the task requirement that deprecated wrappers preserve existing behavior exactly while warning. The public alias-wrapper test only exercises ANSI, so this regression is not caught there. |
| b | 21 | approve | 4 | Five credible defects verified; no fabricated claim identified. | Reviewer had five localized claims, so verification was materially faster than discovering defects from scratch. |
| c | 12 | merge | 5 | 0 defects in the candidate submission. Two unrelated automated PRs identified and excluded. | Replaces adjacency-dependent groupby() with explicit accumulation of every key under its parent; sorting parent groups by path depth preserves the top-down mutation invariant. Checked reversed and interleaved ordering plus a deeper hierarchy — grouping is order-independent. Public regression test covers grouped, interleaved and reversed inputs. |
| d | 28 | request-changes | 5 | 5 real defects + 1 fabricated defect. The fabricated finding is #3, node.ts:94, claiming the altered sibling-conflict check causes the stated route-loss/order-dependent regression. | This Pull correctly identifies the five real defects, but adds one unsupported/fabricated defect. Under W6's precision requirement, that is significant: the prompt explicitly says a false issue counts against the reviewer. D also takes more human time than B because a senior reviewer has to spend additional time tracing and disproving the plausible-looking sixth claim. |
| e | 9 | merge | 5 | 0 defects in candidate submission. Two unrelated automated PRs identified and excluded. | Minimal one-hunk fix, 1 file +3/−4. Replaces adjacency-dependent groupby() with explicit parent-key accumulation via setdefault(). The existing sort by slash-depth is sufficient: keys are scanned in nondecreasing node depth, so parent buckets are inserted in nondecreasing parent depth and grouped.items() still processes top-down, preserving the surrounding mutation assumption. |

Decision values: merge / request-changes / reject
Confidence: 1 = "I'd want a second reviewer", 5 = "I'd merge this on my own authority"

## Fabrication check (recorded before the key was opened)

- Candidate: d
- Claim: finding #3, node.ts:9x — asserted defect not present in the code
- Minutes spent disproving it: <n>
- Candidates a, b, c, e: no false claims identified.

## After opening the key

| Candidate | Run id | Model/arm | Sealed gate verdict | Quality | Fabrications | Cost/attempt | Matched my decision? |
|---|---|---|---|---|---|---|---|
| a | `w3-sqlfluff-segment-method-migration__P0__rep2` | **P0** (Opus) | rejected | unavailable | – | $14.82 | yes — I said request-changes |
| b | `w6-hono-router-review__C2__rep2` | **C2** (Sonnet) | rejected | 4/6 | **1** | $1.42 | **no — I approved it** |
| c | `w4b-zarr-consolidated-order__P0__rep1` | **P0** (Opus) | rejected | unavailable | – | $1.18 | **no — I merged it** |
| d | `w6-hono-router-review__P0__rep1` | **P0** (Opus) | **accepted** | 6/6 | 0 | $3.44 | **no — I said request-changes** |
| e | `w4b-zarr-consolidated-order__C2__rep1` | **C2** (Sonnet) | rejected | unavailable | – | $0.67 | **no — I merged it** |

Verdicts for a, c, d, e are the authoritative regrade-v2 result; b's regrade left the
original verdict unchanged. Costs are per attempt, exact (both arms are Product A).

## Observations
Review cost varied from 9 to 33 minutes per candidate. The biggest driver was not diff size alone, but how much uncertainty I had to resolve before I was comfortable making a merge decision.

Broad migrations took longer because I had to understand architecture, compatibility, and call-site coverage. Narrow one-file fixes were much faster when the reasoning stayed local.

The W6 review reports showed a different pattern: localized findings reduced search time, but a plausible false positive increased review cost because I had to investigate and disprove it before I could trust the report.

The practical takeaway is that human review cost depends heavily on scope, precision, and trustworthiness, not just whether the final code passes a gate.

## Limitations

Scratch review repos inherited upstream `.github/dependabot.yml`, so Dependabot
opened unrelated PRs in some candidate repos. Only the PR titled "Candidate change"
or "Candidate review report" is the artifact under review. Triage of the unrelated
PRs (~2 min each, 4 min total observed on candidate c) is excluded from the recorded
review minutes: it is a harness artifact, not a cost of reviewing model output.

## After opening the key (auto-filled)

| Cand | Run id | Task | Arm | Sealed verdict | Public gate | Quality | Cost/attempt |
|---|---|---|---|---|---|---|---|
| a | `w3-sqlfluff-segment-method-migration__P0__rep2__20260820T114309` | w3-sqlfluff-segment-method-migration | **P0** | rejected | fail | - (fab -) | - |
| b | `w6-hono-router-review__C2__rep2__20260821T114722` | w6-hono-router-review | **C2** | rejected | pass | 4/6 (fab -) | - |
| c | `w4b-zarr-consolidated-order__P0__rep1__20260818T161702` | w4b-zarr-consolidated-order | **P0** | rejected | fail | - (fab -) | - |
| d | `w6-hono-router-review__P0__rep1__20260820T203422` | w6-hono-router-review | **P0** | rejected | fail | 6/6 (fab -) | - |
| e | `w4b-zarr-consolidated-order__C2__rep1__20260818T165043` | w4b-zarr-consolidated-order | **C2** | rejected | fail | - (fab -) | - |

*Auto-filled by `tools/stopwatch-fill.py` from the run artifacts. Cost is the run's own recost figure; `≤` marks a cache-blind upper bound.*
