# Verbatim source extracts — provenance and licence

Every `*.py.txt` file in this directory is a **byte-exact extract** from

    repo: https://github.com/lexha-redstone/tokenomics-benchmark-multi-llms
    sha:  1a18b04385f9a0da16439ba5f48a2f68ac08d53d

licensed Apache-2.0 (`LICENSE` at that sha; each source file carries
`# Copyright 2026. Licensed under the Apache License, Version 2.0.`). They are
kept as `.txt` so nothing here is importable, executable, or discoverable by our
test runner: they are **evidence**, not code. Our implementation lives in
`harness/adapters/transfer_*.py` and is driven by the sibling `*-spec.yaml`
files, which pin these extracts by sha256.

Nothing in this directory was edited, reformatted, or paraphrased. The
extraction was a regex slice of the whole top-level definition; the only
transformation applied was normalising the file to end in exactly one newline.

## Why extracts and not a submodule

The probe reimplements three routing strategies in a harness with a different
oracle, a different cost model, and a different execution posture. What must be
frozen is the *decision logic and the prompts*, not the source's runtime. Byte
pins on the exact definitions we transplanted let a reader check our
reimplementation against the original without cloning anything, and let
`tests/test_transfer_specs.py` fail loudly if either side drifts.

## Files

| File | Source path | What it is |
|---|---|---|
| `run-tiered-router.py.txt` | `src/architectures.py` | the ladder loop all three arms call |
| `gate-after-ladder.py.txt` | `src/routing.py` | r6 / r10's gate (counts rungs) |
| `gate-on-evidence.py.txt` | `src/routing.py` | r9's gate (reads evidence) |
| `classify.py.txt` | `src/routing.py` | evidence graph -> `Difficulty` |
| `classify-guard.py.txt` | `src/routing.py` | pre-suite guard failures -> `Difficulty` |
| `difficulty.py.txt` | `src/routing.py` | the `Difficulty` type, incl. `is_hard` |
| `routing-constants.py.txt` | `src/routing.py` | `BROAD_FAILURE_ITEMS`, class sets, `LEVELS` |
| `solver-role.py.txt` | `src/config.py` | verbatim solver system prompt |
| `repair-role.py.txt` | `src/config.py` | verbatim repair system prompt |
| `build-initial-prompt.py.txt` | `src/architectures.py` | rung-0 prompt assembly |
| `repair-prompt.py.txt` | `src/architectures.py` | repair-turn prompt assembly |
| `fresh-prompt.py.txt` | `src/architectures.py` | r10's fresh-solve prompt assembly |
| `treat-error.py.txt` | `src/architectures.py` | the `$0` contained digest step |
| `eval-solution.py.txt` | `src/architectures.py` | the source's own unit-test oracle call |
| `arm-r9.py.txt` | `src/architectures.py` | r9 registry entry |
| `arm-r6.py.txt` | `src/architectures.py` | r6 registry entry |
| `arm-r10.py.txt` | `src/architectures.py` | r10 registry entry |
| `arm-r0a.py.txt` | `src/architectures.py` | r0a baseline (our C2 anchor) |
| `arm-r0b.py.txt` | `src/architectures.py` | r0b baseline (our P0 anchor) |
