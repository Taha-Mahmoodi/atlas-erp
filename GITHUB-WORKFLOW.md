# GITHUB-WORKFLOW.md — Repository & GitHub Operating Protocol for Atlas ERP

Place this file at the repo root alongside CLAUDE.md, and add this line to CLAUDE.md: "All git and GitHub operations MUST follow GITHUB-WORKFLOW.md. Re-read it after any compaction." You (the agent) use the `gh` CLI for everything GitHub-side: repo creation, PRs, issues, labels, releases.

# 1. Repository Setup (do this once, before any code)

1. Create a **public** repository: `gh repo create atlas-erp --public --description "Open-source, industry-agnostic ERP. Functional benchmark: SAP S/4HANA." --clone`. Because the repo is public from day one: never commit secrets, tokens, API keys, real personal data, or `.env` files — commit `.env.example` instead, and add a `.gitignore` covering env files, virtualenvs, node_modules, build output, and IDE folders as your very first commit.
2. Add at the root: `README.md`, `LICENSE` (Apache-2.0), `CONTRIBUTING.md` (summarizes this workflow for human contributors), `SECURITY.md` (how to report vulnerabilities privately), and `.github/PULL_REQUEST_TEMPLATE.md` plus `.github/ISSUE_TEMPLATE/bug.yaml` and `feature.yaml` matching the formats defined below.
3. Create labels: `bug`, `enhancement`, `tech-debt`, `module:finance`, `module:inventory`, `module:procurement`, `module:sales`, `module:manufacturing`, `module:hr`, `module:core`, `module:frontend`, `module:docs`, `severity:blocker`, `severity:major`, `severity:minor`, `found-during-build`.
4. Create a CI workflow at `.github/workflows/ci.yml` that runs on every PR: backend lint (ruff) + pytest, frontend typecheck + build. A red CI run blocks merging — no exceptions, including for you.

# 2. Branch Model — exactly two long-lived branches

- **`main` = production.** Always releasable. Nothing is ever committed directly to `main`. It only ever receives merges from `dev` via a promotion PR (section 5).
- **`dev` = integration.** All work lands here first, via short-lived feature branches.
- **Feature branches** are cut from `dev`, named `feat/<module>-<short-slug>`, `fix/<issue-number>-<short-slug>`, or `docs/<short-slug>`. One branch = one task from PLAN.md or one issue. Delete the branch after its PR merges. Never let a feature branch live longer than one task — long-lived feature branches are how you lose state across compactions.
- Set `main` as the default branch on GitHub, and enable branch protection on both `main` and `dev` requiring CI to pass before merge (`gh api` or repo settings).

# 3. Commit Discipline

- Use Conventional Commits: `feat(finance): reject journal entries with unbalanced lines`, `fix(inventory): correct FIFO layer consumption on partial issue (#23)`, `test(sales): add credit-limit block coverage`, `docs(readme): add ERD`. Types: `feat`, `fix`, `test`, `docs`, `refactor`, `chore`, `ci`.
- One logical change per commit. A commit must leave the codebase in a working state — tests passing — because commits are also your recovery checkpoints after compaction.
- Commit body (the detail level): 2–6 lines explaining **why**, not what (the diff shows what). State the business rule or invariant involved, any alternative you rejected, and reference the PLAN.md task number and any issue (`Refs PLAN 4.3`, `Fixes #23`). A future maintainer reading only `git log` should be able to reconstruct the reasoning of the build.
- Never use `--force` on `dev` or `main`. Never amend or rebase commits that have been pushed to a shared branch.

# 4. Pull Requests into `dev`

Every task merges to `dev` through a PR — even though you are the only contributor — because PRs are the project's reviewable history and your own audit trail. Open with `gh pr create --base dev`.

**PR title:** same convention as commits, scoped to the task: `feat(finance): double-entry journal engine with period close`.

**PR description — required sections, this is the expected level of detail:**
1. **Summary** — 2–4 sentences: what this delivers in business terms ("Posting a goods receipt now creates an inventory-debit / GR-IR-credit journal automatically").
2. **Design notes** — the decisions made and why, mirroring what was added to DECISIONS.md. Include rejected alternatives if any were seriously considered.
3. **Invariants enforced** — list any business rules this PR adds or relies on (e.g., "debits must equal credits per currency, enforced in service layer + DB CHECK").
4. **Tests** — what is covered, what intentionally isn't yet, with the issue number for the gap.
5. **Linked items** — `Refs PLAN x.y`, `Closes #NN` for every issue resolved.
6. **Out of scope** — anything noticed but deliberately not done here (each must have an issue, see section 6).

Apply the relevant `module:*` label. Before merging: confirm CI is green, re-read your own diff once (`gh pr diff`) looking specifically for secrets, debug prints, and tenant-filter bypasses, then merge with **squash** (`gh pr merge --squash --delete-branch`) so `dev` history stays one-commit-per-task. The squash commit message must keep the PR title and a condensed body.

# 5. Promotion: `dev` → `main`

Promote when a milestone is complete and stable — at minimum after each major phase of PLAN.md (core complete, finance complete, all backend modules complete, frontend complete, v1 final). Never promote mid-task.

Promotion procedure:
1. On `dev`: full test suite green, `docker-compose up` verified working, PROGRESS.md and the parity doc updated.
2. Open a **promotion PR** `dev → main` titled `release: <milestone name>` (`gh pr create --base main --head dev`). Its description is a **changelog**: every squashed PR since the last promotion grouped under Added / Fixed / Changed, the list of issues closed, known issues still open (with numbers), and any migration or breaking-change notes. This description is the release notes — write it for an outside user of the public repo, not for yourself.
3. Merge with a **merge commit** (`gh pr merge --merge`), NOT squash — `main`'s history should show promotions as merge points while preserving traceability to dev.
4. Tag the merge commit semver: `v0.1.0` (core), `v0.2.0` (finance), … `v1.0.0` (final), and create a GitHub release: `gh release create v0.x.0 --notes-from-tag` or paste the changelog. 
5. Never cherry-pick individual commits to `main`. If production needs an urgent fix, branch `fix/...` from `main`, PR it back to `main`, then immediately merge `main` back into `dev` so the branches never diverge.

# 6. Issue-First Bug & Debt Handling (mandatory)

When you discover ANY problem mid-build — a bug, a design flaw, missing validation, a test gap, tech debt — you do not silently fix it. The protocol is **file first, fix second**:

1. **File the issue immediately** with `gh issue create`, labels `found-during-build` + `bug`/`tech-debt` + `module:*` + `severity:*`. Required body:
   - **What's wrong** — observed behavior vs. expected, with the exact file/function.
   - **Reproduction** — the failing input, test, or scenario.
   - **Impact** — which invariant or feature it threatens (e.g., "allows posting to a closed period via the API but not the UI — financial-integrity blocker").
   - **Proposed fix** — your initial plan, 1–3 lines.
2. **Triage by severity:** `severity:blocker` (breaks a financial/stock invariant, tenant isolation, or auth) — stop current work and fix it now. `severity:major` — fix before the current module's PR merges. `severity:minor` — leave it open, schedule it before the next promotion to `main`. Update PLAN.md with a task entry for every non-blocker issue so it can't be forgotten after compaction.
3. **Fix on a branch** named `fix/<issue-number>-<slug>`. The fix PR must: reference `Closes #NN`, include a regression test that fails without the fix and passes with it (no fix merges without one), and explain root cause in the Design notes — not just the symptom.
4. **Close via merge**, never manually, so the issue links to the fixing PR. If investigation shows the issue was invalid, close it with a comment explaining why — never close silently.
5. An issue may NOT be open and untracked at promotion time: every open issue at a `dev → main` promotion must appear in the promotion PR's "known issues" section.

# 7. Documentation Handling

- Docs live in the repo, versioned with the code: `README.md` (front door: what Atlas is, the S/4HANA benchmark framing, screenshots, <10-step quickstart, architecture + ERD Mermaid diagrams), `docs/` (architecture.md, module guides — one per module, written as you finish each module, not at the end —, api.md pointing at the OpenAPI spec, industry-templates.md, and `docs/research/s4hana-parity.md`), plus CONTRIBUTING.md and SECURITY.md.
- **Docs are part of the task**: a module's PR is not complete without its module guide updated. `docs(...)`-only changes still go through feature branch → PR → `dev`.
- The internal state files (PLAN.md, PROGRESS.md, DECISIONS.md, CLAUDE.md, this file) are committed too — in a public repo they double as a transparent build journal. Keep their tone professional; they will be read by strangers.
- README badges: CI status, license, latest release. Update the README's feature list at every promotion so `main`'s README never advertises something `main` doesn't contain.

# 8. Public-Repo Hygiene (continuous)

- Before EVERY push: scan the diff for secrets, internal URLs, personal data, and seed data containing realistic-looking real names/emails (use clearly fictional seed identities and `example.com` emails).
- If a secret ever lands in history: rotate it immediately, then file a `severity:blocker` issue documenting the exposure and remediation.
- All third-party code/licenses must be compatible with Apache-2.0; note any attributions in a `NOTICE` file.

# 9. Self-Check Loop

At the end of every work session (and after any compaction recovery), run this checklist and append the result to PROGRESS.md: working tree clean? current branch correct? all merged branches deleted? CI green on `dev`? any discovered-but-unfiled problems? any open `severity:blocker`? docs current for everything merged? If any answer is bad, fixing it is the next task.
