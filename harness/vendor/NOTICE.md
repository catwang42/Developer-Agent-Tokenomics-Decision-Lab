# Vendored third-party code

Files here are **not this lab's work** and are not edited. Each one is a
byte-exact copy of an upstream file at a pinned revision; the sha256 below is
over the bytes as vendored, and `tests/test_vendored_straitjacket.py` re-hashes
them on every test run. If a hash moves, the copy was edited and the fidelity
claim that depends on it is void.

## `straitjacket.py`

The source benchmark's own wrapper around the capture harness.

| | |
|---|---|
| Repo | https://github.com/lexha-redstone/tokenomics-benchmark-multi-llms |
| Commit | `1a18b04385f9a0da16439ba5f48a2f68ac08d53d` |
| Path | `src/straitjacket.py` |
| sha256 | `b67f81be502c427030d87f6ebf68ad9c1f87ff5f950bb87a8455c9482dadc35b` |
| Licence | Apache-2.0 |

Vendored because `ctx.digest.base.DigestContext.load` requires a `Store`, a
`Workspace` and a stream manifest that only this wrapper constructs. Calling
`ctx` directly from our own code would mean reimplementing that construction,
and a reimplementation is exactly the thing the calibration is supposed to
detect rather than contain.

It is used by the r9 calibration evidence path only — `harness/vendor/sj_capture.py`
imports it, and nothing else in this repository does.

## `sj_capture.py`

**Ours**, not vendored, and the only file in this repository that talks to
`ctx`. It exists because `ctx-harness` requires Python >= 3.11 while this lab's
harness runs on 3.10; see the module docstring. It reproduces
`evaluator._run_bigcodebench_contained` from the same pinned revision and makes
no selection of its own.

## `ctx-harness` (installed, not vendored)

| | |
|---|---|
| Repo | https://github.com/vamsiramakrishnan/straitjacket |
| Commit | `7c69ea70aa40e1017aa6114b19e977225dd4166f` |
| Package | `ctx-harness` 0.35.1 (hatchling, import root `ctx`) |
| Installed package dir sha256 | `016aca7bf3a2424d78d0e35fc0938acdf877bc393b2998a82f88609a1f5b5f33` |
| Interpreter | CPython 3.12.14 at `~/.cache/lab-ctx-venv/bin/python` |
| Author confirmation | **pending** |

The package-dir hash is over the 144 non-`.pyc` files under the installed `ctx`
package: `find . -type f ! -name '*.pyc' | sort | xargs sha256sum | sha256sum`.

"Author confirmation pending" is recorded because the identification of this
repository as the source's `ctx run` harness is this lab's inference from the
digest header (`[ctx run:<id> profile=<profile>]`), the package name and the
API surface `straitjacket.py` calls. The upstream author has not confirmed it.
The pin is exact and the evidence is reproducible either way; what is
unconfirmed is the claim that this is *the* harness the published rows were
produced with.
