# Fix: agy usage was never captured

**No spend. No agent runs. Do not touch `results/`.**

## The defect

`harness/adapters/agy.py:build_command` never passes `--output-format json`. agy's
default is `text`, so `json.loads(proc.stdout)` has thrown on every Gemini run ever
made, `payload` was always `None`, and `usage_from_agy_json` marked all six token
classes `unavailable`. Verified: 0 of 153 archived `invocation.txt` files contain a
usage block, across all four datasets.

agy DOES expose usage. Verified 2026-08-22 on agy 1.1.13:

```json
"usage":{"input_tokens":12733,"output_tokens":31,"thinking_tokens":30,
         "cache_read_tokens":0,"total_tokens":12764}
```

A second latent bug sits behind the first: the mapper looks for `reasoning_tokens`;
agy emits `thinking_tokens`. Fixing only the flag would silently drop the thinking
class.

## Task 1 — pass the flag

Add `--output-format json` to `build_command`. Update the docstring's verified-invocation
notes to record that the flag is required for usage capture and that its absence was the
cause of Product-B cost unavailability across screening batch 1.

Note in the docstring: `stream-json` also emits usage per step, which would give
per-turn attribution. Do not switch to it — that is a run-condition change and belongs
to the human.

## Task 2 — map the thinking class

In `usage_from_agy_json`, accept `thinking_tokens` as an alias for the canonical
`reasoning_tokens` field. Record which source key was found so provenance stays
inspectable. Preserve any unmapped usage keys verbatim in the emitted event under
`unmapped_usage_keys`.

Rules that do not change:
- absent classes stay `unavailable`, never zero — `cache_creation_tokens` is genuinely
  absent from agy's block and stays unavailable
- tier stays `proxy_observed`, never `authoritative`

## Task 3 — tests

In `tests/test_agy_adapter.py`:
- `build_command` includes `--output-format json`
- payload with `thinking_tokens` maps to the reasoning field at `proxy_observed`
- payload with `reasoning_tokens` still maps
- payload with neither leaves it `unavailable`
- unknown extra key is preserved in `unmapped_usage_keys`
- empty stdout still behaves (the existing C3 no-output finding must not regress)

Run `bash tests/run-tests.sh`.

## Task 4 — write the finding

Create `report/findings/agy-json-flag-defect.md`:

- what the defect was, the exact missing flag, and the one-line evidence (0/153)
- that the provider-side collector, quiet-window protocol, contamination guard and the
  v1→v2→v3 attribution rules were all built to work around it
- that `cache_read_tokens` is exposed by the product, which bears on the 2026-08-16
  cache-blindness decision (`gemini_cache_blindness`, taken on provider-metric evidence
  with no probe run) — flag for human review, change no pins
- that recovery from archives is impossible: pricing any Gemini cell requires re-running
- self-caught instrument defect; number it in sequence with the existing six

Do not edit `manifest/cp-findings.md`. Do not edit any manifest pin. Do not re-run
anything.

## Report

```
FLAG      build_command now passes --output-format json: yes/no
MAPPING   thinking_tokens alias: yes/no   unmapped keys preserved: yes/no
TESTS     <pass/fail>
FINDING   report/findings/agy-json-flag-defect.md written: yes/no
SMOKE     <if a zero-cost dry-run path exists, the built command line, verbatim>
```

Then stop.
