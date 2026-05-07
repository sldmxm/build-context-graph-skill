# Bootstrap Checklist

Use this checklist when rolling the memory system into a repository.

## Phase 1: Inventory

- Read `AGENTS.md`, `README.md`, and existing `.agents/` content.
- Check for an existing `.agents/context-graph` or alternative memory layer.
- Identify docs that likely contain durable rules: deploy runbooks, migration
  docs, CI workflow docs, ownership rules, compatibility rules.

## Phase 2: Install

- Run the skill installer to copy `scripts/repo_memory/`.
- Bootstrap `.agents/context-graph/`.
- Do not overwrite existing traces or policies without reading them first.

## Phase 3: Audit

- Run `python -m scripts.repo_memory.audit --repo-root .`.
- Review `policy_candidates`.
- Review `promotion_candidates`.
- Decide which findings should become curated traces and which should become
  stable policies.

## Phase 4: Seed

- Capture 2-5 curated traces for the highest-value architecture or workflow
  decisions first.
- Add 1-3 policies for rules that repeatedly constrain changes.
- Update `AGENTS.md` so future agents query memory before reading code.

## Phase 5: Validate

- Run `python -m scripts.repo_memory.validate --repo-root .`.
- Run at least one query that should surface the new traces or policies.
- Confirm the query results are useful before calling the rollout complete.

## Minimum Success Bar

- The repo has `.agents/context-graph/` scaffolded.
- The repo has `scripts/repo_memory/` installed.
- `AGENTS.md` tells agents how to query the memory layer.
- At least one curated trace exists for an active engineering decision.
- At least one stable policy exists if the repo has clear long-lived rules.
