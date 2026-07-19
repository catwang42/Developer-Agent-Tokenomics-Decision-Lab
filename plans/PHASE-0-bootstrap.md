# Phase 0 — Bootstrap & Hygiene
**Goal:** repository is buildable, testable, CI-green, with zero live-API dependencies.
**Branch:** phase/0-bootstrap

## Tasks
1. Replace LICENSE placeholder with full MIT text (owner from git config).
2. Create tests/run-tests.sh skeleton that: validates all JSON/YAML in the repo,
   runs shellcheck on all *.sh, exits non-zero on any failure. Dependency-light
   (python3 stdlib + shellcheck; install shellcheck via apt if absent).
3. Verify .github/workflows/ci.yml and deploy-pages.yml parse (yamllint or python yaml).
4. mkdocs build --strict passes with the stub docs (pip install mkdocs-material).
5. Confirm .claude/settings.json deny/ask rules load (start summary in PR description).

## Acceptance checklist
- [ ] bash tests/run-tests.sh exits 0 and reports what it checked
- [ ] shellcheck clean; all JSON/YAML valid; mkdocs build --strict clean
- [ ] PR opened with evidence pasted
**Checkpoint:** none (hygiene only).

## Backlog (deferred hygiene)
- **Pin the shellcheck version between local and CI.** CI installs shellcheck via
  `apt-get` (ubuntu-latest → 0.9.x), which introduced diagnostics absent from older
  local versions (e.g. 0.7.1) — SC2317 "unreachable" on trap-only handlers, later
  renamed SC2329 in 0.11.x. This surfaced as a Phase 2 CI failure not reproducible
  locally. Fix: pin a fixed shellcheck version in ci.yml (and document/match it for
  local dev), so `shellcheck` clean means the same thing in both places.
