# The seven-point audit checklist

The canonical wording, and its single canonical home. ex130 (cold audit of a circulated
benchmark) and ex410 (peer audit of your own memo) both link here; no other page
restates the list, so there is one wording everywhere.

**self-reported tokens · unmeasured claims · confounded variables · cache-blind math ·
no quality gate · n=1 · decorative extrapolation**

Use it twice. First on someone else's number — read the artifact cold, list what is
wrong, *then* open this page and map your findings onto the seven points. Second on your
own: any recommendation you write is fair game, including one that leans on this lab's
numbers past their scope lines.

---

## 1. Self-reported tokens

The model told you what it spent. That is not a measurement — it is generated text that
happens to contain digits, produced by the same system whose cost is in question. A
usage figure counts only when it comes from the product's own machine-readable usage
metadata or the provider's billing plane. If a benchmark's token counts came out of a
transcript, out of a "summarize your usage" prompt, or out of a tokenizer estimate
applied after the fact, the number is an estimate wearing a measurement's clothes. Ask
where the field was read from, and what happens to the figure when the answer is
"nowhere" — the honest answer is `unavailable`, never zero.

## 2. Unmeasured claims

The claim in the headline is not the thing the experiment measured. A run that recorded
tokens and wall-clock does not support a claim about developer productivity, code
quality, or maintenance burden; a run on one repository does not support a claim about
"engineering work." Read the claim, then read the method, and write down the gap between
them. Most of the persuasive force in a circulated benchmark lives in that gap — the
measurement is usually real and usually narrower than the sentence it is used to
support.

## 3. Confounded variables

Two things changed, so neither is the cause. Comparing product A on model X against
product B on model Y varies the product **and** the model **and** the orchestration
**and** the billing path at once: the result is a fact about two complete stacks, not
about either model. This is not a reason to refuse the comparison — whole-stack
comparisons are what buyers actually choose between — it is a reason to label it. A
finding is a *product black-box* result, a *within-product model* result, or a *routing
policy* result, and those three never merge into one chart or one causal sentence.

## 4. Cache-blind math

Tokens have at least four prices, not one. Fresh input, cache-write, cache-read and
output bill at materially different rates, and a context window replayed across turns is
mostly cache reads. Multiply a total context count by the list input price and you get a
number that can overstate the real bill by a wide margin — or, on a stack that exposes
no cache breakdown at all, a number whose error you cannot even bound. When you are
shown "N input tokens × $X per million," the question is always *at what cache rate?* If
the breakdown does not exist, say so and price the run as a declared upper bound; do not
quietly pick one rate.

## 5. No quality gate

Cheap output that does not work is not cheap. A cost comparison without an acceptance
criterion is a comparison of how fast each configuration produced *something*, and the
configuration that produces plausible-looking work fastest will win it. The gate has to
be pre-registered, independent, and deterministic-first — hidden tests, type checks,
regression checks decide — with human review timed rather than assumed, and the
generating model never the sole judge of its own work. Then cost is charged per
**accepted** outcome, with failed attempts billed to the configuration that failed, not
averaged away.

## 6. n=1

One run per arm measures the run, not the configuration. Identical pinned runs of the
same task spread by a task- and tier-dependent factor, so whichever arm happened to draw
the low sample looks like the winner, and a POC decided on one run each is a coin flip
with a spreadsheet attached. Never accept a point estimate: demand the median, the
range, and n, and budget with the band rather than the point. If the sample is too small
for an interval, that is a finding to publish, not a detail to omit.

## 7. Decorative extrapolation

The measured number is small and real; the headline number is large and invented. A
per-task saving multiplied by an assumed task volume, an assumed adoption rate and an
assumed loaded rate produces an annual figure whose precision comes entirely from the
assumptions — and runtime converted into headcount is the sharpest version of this,
because it prices work that was never measured. Ask which of the inputs was observed and
which was chosen. Extrapolations belong in a clearly labeled scenario with its
assumptions on the same page, never in the headline.

---

## Using it

- **Every finding travels with its scope line** — the task, the conditions, the cost
  basis, and n. A number without its scope line is not portable, including ours.
- **Eliminate before you rank.** Governance constraints and the quality gate are
  lexicographically prior to cost. A configuration that fails non-inferiority is
  eliminated, not discounted.
- **A recommendation without its break-even conditions is an advertisement.** State the
  conditions under which your own recommendation flips.
