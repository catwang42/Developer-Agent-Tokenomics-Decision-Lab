# Sealed Evaluation — how work is graded, and why you can trust the grade

This page explains, in plain language, how the lab decides whether an agent's work
is *accepted*. It is written for two audiences: people using this repository, and
people taking part in a lab session. No prior knowledge is assumed.

## Why hidden tests exist

Every task in this lab is graded by tests. Some of those tests are published with
the task so you know what "good" looks like; others are kept hidden. The reason is
simple: if an agent (or a person) can see *every* test in advance, the tests stop
measuring whether the work is correct and start measuring whether it was tailored
to the tests. Code can be written to pass a specific check while still being wrong —
for example, a test suite that runs every line of a function but never checks that
the answers are right. Hidden tests close that gap. They are run only after the work
is submitted, so a passing result means the work actually behaves correctly, not
just that it matched a visible target.

## Who holds them

The hidden tests are held by the **evaluation operator** — the person or team running
the measurement — and never live in the repository. They are excluded from version
control and are never committed, published, or shared with the agent being measured.
This separation is deliberate: the party doing the work and the party holding the
answer key are kept apart, so no run can be graded against material the agent could
have seen. In this project the visible task, the public tests, and the evaluator's
version are all open; only the hidden set stays sealed.

## What the hash on every result proves

Because the hidden tests are secret, you cannot simply read them to confirm a result
was graded fairly. Instead, every result records a **hidden-test hash** — a short,
fixed-length fingerprint computed from the exact hidden tests used to judge that run.
The same tests always produce the same fingerprint, and any change to them produces a
different one. This lets anyone confirm, after the fact, that a whole batch of results
was judged by the *same* sealed set, and lets the operator later publish the tests and
show they match the fingerprint on file — all without revealing the tests while an
evaluation is still open.

## The rotation-and-release lifecycle

Hidden tests follow a defined lifecycle (SPEC §2.6). During an active evaluation cycle
they stay sealed, and their version and hash are recorded on every result. A canonical,
known-correct solution is kept and checked against the hidden set the whole time, so the
tests are known to be sound before anyone is graded by them. When a cycle ends, the
tests are either **rotated** — replaced with a fresh set for the next cycle, so past
exposure cannot help future runs — or **released** — published openly once they no
longer need to stay secret. Either way, participants never have access to the sealed
tests during a run.

## Authoring your own set (fork operators)

If you fork this repository to run your own measurements, you become the evaluation
operator and author your own hidden tests. Each task that needs a sealed set ships a
`README-FOR-HUMAN.md` in its `hidden/` directory describing exactly what that set must
do and the pass/fail contract it must honor. You write your tests there following that
spec; the directory is already ignored by version control, so your set stays private by
default. The harness then discovers your tests, records their version and hash on every
result, and runs a ten-point validation to confirm the canonical solution passes and an
unmodified task fails — proving your set is a sound grader before you measure anyone with
it.
