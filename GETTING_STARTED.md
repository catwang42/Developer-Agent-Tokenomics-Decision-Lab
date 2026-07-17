# Getting Started — Building the Lab with Claude Code

You approve checkpoints; Claude Code does the rest. Total human touch points: ~7 per
full build (one per checkpoint) plus PR merges.

## 0. Prerequisites (once)
- Git + a GitHub account + the GitHub CLI (`gh auth login`)
- Node.js 18+ and Python 3.10+
- Claude Code: `npm install -g @anthropic-ai/claude-code`, then run `claude` once to
  log in. Docs: https://docs.claude.com/en/docs/claude-code/overview
- (Phases 3–4 only) provider credentials for the benchmark subjects: Anthropic API/
  subscription for Product A; Google Cloud auth + Antigravity CLI for Product B.

## 1. Create the repository
```bash
cd agent-economics-lab
git init -b main && git add -A && git commit -m "chore: scaffold v2.1.1"
gh repo create agent-economics-lab --public --source=. --push
```
Public repo = free GitHub Pages. Then on GitHub: **Settings → Pages → Source: GitHub
Actions** (the deploy workflow is already in the repo).

## 2. The build loop (repeat per phase, 0 → 6)
```bash
claude --permission-mode plan     # start read-only; or press Shift+Tab to cycle modes
```
Kickoff prompt (adjust N):
> Read CLAUDE.md and SPEC.md fully. Then read plans/PHASE-N-*.md and propose your
> implementation plan for Phase N only — files, commands, verification. Do not write
> anything yet.

Then:
1. **Review the plan.** Push back until it names files and verification. Approve.
2. **Execution:** switch to accept-edits (Shift+Tab) so file edits flow without
   per-edit prompts. The `.claude/settings.json` in this repo still forces an ask on
   anything that spends money (`claude -p`, `agy`, `gcloud`) or pushes — that is your
   safety net, keep it.
3. **Checkpoints:** when Claude prints `CHECKPOINT REQUIRED: <ID>`, verify exactly the
   listed items, then reply `CHECKPOINT APPROVED: <ID>` (or give corrections). This is
   your only critical intervention. CP-SPEND additionally needs your credentials
   exported and the cost estimate sanity-checked.
4. **Phase end:** Claude runs the quality gates and opens a PR (`gh pr create`).
   Review the diff on GitHub, merge, then in Claude Code: `/clear`, next phase.

## 3. Automation dial (choose per phase)
- **Recommended (phases 1–4):** interactive, plan-first, accept-edits during execution.
- **Low-risk phases (0, 5):** more autonomy is fine:
  `claude --permission-mode acceptEdits "Execute plans/PHASE-0-bootstrap.md per CLAUDE.md; stop at any checkpoint."`
- **Headless (CI-style, no-spend phases only):**
  `claude -p "Execute plans/PHASE-0-bootstrap.md per CLAUDE.md" --max-turns 40 --max-budget-usd 5`
  Never run spend-gated phases headless — checkpoints need you.
- Resume an interrupted phase: `claude --resume` (or `claude --continue`).

## 4. What each checkpoint is really checking
| CP | Your 5-minute job |
|---|---|
| CP-SCHEMA | Schema fields match SPEC §2.7; validator rejects zero-fills |
| CP-TASK | validate.sh 10/10 in clean container; author hidden tests (they stay out of git) |
| CP-SPEND | Manifest + pricing pinned, cost estimate sane, creds scoped |
| CP-DATA | Completeness report honest; no vendor claims |
| CP-SCREEN-PREREG | All 5 pre-registrations before any run; anti-bias rules present |
| CP-FINDINGS | Numbers scoped, both cost views, C2 comparison present |
| CP-PUBLISH | External page respects the claims register |

## 5. Ground rules that keep it safe
The repo enforces them: SPEC.md/CLAUDE.md are deny-listed from edits;
results/pilot-reference is write-protected; spend commands always ask; results never
contain synthetic data; `main` only via PR. If Claude ever proposes bending one of
these, that is your cue to say no — the rule is the product.
