#!/usr/bin/env python3
"""Diff-scope classifier for the test-generation gate (check T1), parameterized so
the bash gate stays a thin orchestrator and the (error-prone) classification is
unit-testable offline (tests/test_gate_logic.py).

The test-generation contract: the agent may ONLY ADD new files under
`agent_write_scope` (e.g. src/tests/). Any modification/deletion/rename of a tracked
file (mappers, config, existing tests — anything), and any new file OUTSIDE the
scope, is a violation. This checks the CONTRACT (add-only under scope), not any one
test-file name or shape.

CLI:  scope_eval.py <write_scope> [target_path ...]   # `git status --porcelain
      --untracked-files=all` on stdin
  stdout, one record per line:
    TEST\t<path>   a NEW test file under the scope (to be graded by T2/T3/T4)
    AUX\t<path>    a NEW non-test file under the scope (allowed; e.g. a fixture)
    BAD\t<detail>  a violation (out-of-scope add, or any tracked-file change)
  exit 0 = no violations; 1 = one or more violations; 2 = usage error.
"""
from __future__ import annotations

import sys

TEST_SUFFIXES = (".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx",
                 ".test.js", ".spec.js")


def _under(path: str, scope: str) -> bool:
    scope = scope.rstrip("/") + "/"
    return path.startswith(scope)


def classify(porcelain: str, write_scope: str, target_paths):
    """Classify `git status --porcelain -uall` output.

    Returns (violations, test_files, aux_files) as lists of strings. `violations`
    holds human-readable details; `test_files`/`aux_files` hold repo-relative paths.
    """
    targets = set(target_paths or [])
    violations, test_files, aux_files = [], [], []
    for raw in porcelain.splitlines():
        if not raw.strip():
            continue
        # Porcelain v1: 2 status chars, a space, then the path (untracked == "??").
        xy, path = raw[:2], raw[3:]
        if xy == "??":
            if _under(path, write_scope):
                (test_files if path.endswith(TEST_SUFFIXES) else aux_files).append(path)
            else:
                violations.append(f"{path} (new file outside {write_scope})")
        else:
            # Any change to a tracked file is forbidden — the agent adds, never edits.
            code = xy.strip() or xy
            note = " [target/product]" if path in targets else ""
            violations.append(f"{path} ({code}){note}")
    return violations, test_files, aux_files


def main(argv) -> int:
    if len(argv) < 2:
        print("usage: scope_eval.py <write_scope> [target_path ...]", file=sys.stderr)
        return 2
    write_scope, targets = argv[1], argv[2:]
    porcelain = sys.stdin.read()
    violations, test_files, aux_files = classify(porcelain, write_scope, targets)
    for p in test_files:
        print(f"TEST\t{p}")
    for p in aux_files:
        print(f"AUX\t{p}")
    for v in violations:
        print(f"BAD\t{v}")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
