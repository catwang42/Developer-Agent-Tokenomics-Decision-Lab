# Phase 2 — Pilot Task Validation (SPEC §2.8 / §2.4 task rules)
**Goal:** the RealWorld pilot task passes the 10-point validation from a clean
container; hidden-test scaffolding ready (hidden tests themselves are HUMAN-HELD).
**Branch:** phase/2-pilot-task

## Tasks
1. tasks/pilot-realworld/: setup.sh (clone gothinkster/node-express-realworld-example-app
   at the pinned commit recorded in manifest/delivery-manifest.yaml; verify SHA),
   reset.sh (deterministic reset), Dockerfile or devcontainer for clean builds.
2. validate.sh implementing all 10 checks from SPEC §2.8 (commit exists; deps/ORM at
   commit; paths exist; clean install; baseline tests pass; task fails pre-modification;
   canonical-patch passes hidden gate; no leakage; clean-container build; deterministic
   reset). Output a machine-readable validation report JSON + human-readable summary.
3. Public teaching gate: gate/check-public.sh (the visible 9-check version).
4. Hidden-test scaffold: gate/check-hidden.sh loads tests from tasks/hidden/ (gitignored)
   and records their version+hash into every result (SPEC §2.6 sealed policy). Write
   tasks/hidden/README-FOR-HUMAN.md explaining what the human must author and where.
5. Canonical solution patch under tasks/pilot-realworld/canonical/ to prove check 7.

## Acceptance checklist
- [ ] validate.sh runs end-to-end in a clean container; report shows 10/10 (or lists
      exactly which checks await the human-held hidden tests)
- [ ] reset.sh proven idempotent (run twice, identical tree hash)
- [ ] tests green, shellcheck clean
**Checkpoint: CP-TASK** — human reviews validation report; authors/approves hidden tests.
