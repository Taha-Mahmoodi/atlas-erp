# Contributing to Atlas ERP

Thanks for your interest. This repo runs on a strict, documented workflow — the short version is below; the binding details live in [GITHUB-WORKFLOW.md](GITHUB-WORKFLOW.md) (git/GitHub protocol) and [STRUCTURE.md](STRUCTURE.md) (file placement, naming, size limits, dependency rules).

## Branch model

- `main` is production: always releasable, receives only promotion PRs from `dev`.
- `dev` is integration: all work lands here through short-lived feature branches.
- Branch names: `feat/<module>-<slug>`, `fix/<issue-number>-<slug>`, `docs/<slug>`. One branch = one task or one issue. Delete after merge.

## Commits & PRs

- Conventional Commits (`feat(finance): …`, `fix(inventory): … (#23)`); one logical change per commit; every commit leaves the tree green.
- Commit bodies explain **why** (business rule, invariant, rejected alternatives), not what.
- Every PR into `dev` uses the [PR template](.github/PULL_REQUEST_TEMPLATE.md) sections (Summary, Design notes, Invariants enforced, Tests, Linked items, Out of scope), carries a `module:*` label, and merges **squash** only after CI is green.

## Issue-first rule

Found a bug, design flaw, or tech debt? **File the issue before fixing it** (templates provided), labeled `found-during-build`/`bug`/`tech-debt` + `module:*` + `severity:*`. Fixes branch from `fix/<issue>-<slug>`, must include a regression test that fails without the fix, and close the issue via the PR (`Closes #NN`).

## Code rules that will come up in review

- Service layer owns business logic; routers stay thin; models stay logic-free.
- Financial invariants are enforced in code **and** DB constraints.
- Multi-tenancy: never write a query that could bypass the tenant filter.
- Terminology lock: `item`, `vendor`, `customer`, `warehouse`, `journal entry` — same word everywhere.
- File size caps: 400 lines Python, 300 lines TSX; split per STRUCTURE.md §3/§4.
- Tests mirror source paths exactly; test names state the rule being proven.

## Licensing

Contributions are accepted under Apache-2.0. Don't submit code with incompatible licenses; note required attributions in [NOTICE](NOTICE).
