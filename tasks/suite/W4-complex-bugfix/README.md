# W4 — complex bugfix (`w4-realworld-missing-user-id`)

The suite's **first commit-mining exemplar** (WORKLOAD-SELECTION.md §4) and the W4
complex-bugfix workload (SPEC §5.1). Validated with the shared task harness.

## Task (commit-mined)

Derived from a real merged upstream fix in the RealWorld/Conduit API
(`gothinkster/node-express-realworld-example-app`, MIT):

- **Canonical fix commit:** `30b68e1` — *"fix: missing user id"*.
- **Pinned commit (task start):** `88b258c` — its parent, where the bug is present.

`getCurrentUser()` (`src/app/routes/auth/auth.service.ts`) selects the user's
fields from Prisma but omits `id`, so the returned profile has no `id` and the JWT
is signed with an undefined id. The agent must reproduce the one-line upstream fix
(`+ id: true` in the `select`). Commit-mining yields the pre-modification failure
proof for free and an authentic acceptance criterion.

## Contamination tier: `famous` (documented)

RealWorld/Conduit is a canonical, widely-forked teaching app — strongly present in
training data. Recorded per run as `identity.contamination_tier: famous`.

**What it does NOT license (SPEC §5.2 / WORKLOAD-SELECTION §3):** a class-level W4
claim needs a **second, materially different** task at tier `obscure` or
`post_cutoff`. This `famous` task is a screening signal only. Because it is
commit-mined, mining a *post-cutoff* PR in a low-visibility repo is the natural way
to source that second task.

## Run

```bash
TASK_DIR=tasks/suite/W4-complex-bugfix bash harness/task-tools/validate.sh
# shipped: 9 pass + 1 awaiting-human (check 7); 10/10 with sealed/synthetic hidden tests
```

See `harness/task-tools/README.md` for the engine, the DB-free baseline scope
rationale, and the pre-modification-failure interpretation.

## Files

`task.yaml` · `canonical/fix-missing-user-id.patch` (authentic upstream fix) ·
`tests/getCurrentUser.repro.test.ts` (public repro) ·
`hidden/README-FOR-HUMAN.md` (sealed-test authoring plan) · `workload.yaml`
(screening metadata). The subject repo clones into `.work/` (gitignored).
