---
name: build-context-graph
description: Set up, upgrade, or maintain repo-local engineering memory in `.agents/context-graph`. Use for decision traces, durable policies, retrieval workflows, and reconciling current-task traces after review or before commit.
---

# Build Context Graph

Install a lightweight repo-local memory system for engineering decisions, then
use it to keep durable rules and high-signal task traces discoverable.

After bootstrap, prefer the repo-local toolkit under
`.agents/context-graph/tools/repo_memory/` over the skill's own bootstrap
script. Use the repo-local toolkit for daily operation. For review follow-ups
or commit preparation, read [trace-maintenance.md](references/trace-maintenance.md).

## Workflow

### 1. Inspect the repository first

- Read `AGENTS.md`, top-level `README.md`, and any existing `.agents/` layout.
- Check whether the repo already has `.agents/context-graph` or a similar
  memory system.
- If the repo already has traces or policies, preserve them. Upgrade in place
  instead of replacing them blindly.

### 2. Bootstrap or upgrade the toolkit

Run the installer from this skill:

```bash
python /path/to/build-context-graph/scripts/bootstrap_repo_memory.py \
  --repo-root /path/to/repo
```

This installs a repo-local toolkit under
`.agents/context-graph/tools/repo_memory/` and creates the
`.agents/context-graph/` scaffold.

If the repo already has `.agents/context-graph/tools/repo_memory/`, rerun with
`--force` only after reviewing local edits. The installer is intentionally
additive: it should not delete existing traces or policies.

### 3. Audit the repository for seed material

From the target repository root, run:

```bash
PYTHONPATH=.agents/context-graph/tools python -m repo_memory.audit --repo-root .
```

Use the audit report to find:

- stable-rule candidates in `AGENTS.md`, docs, CI, migrations, or runbooks;
- traces that should be promoted into policies;
- the retrieval snippet to place into `AGENTS.md`.

Read [bootstrap-checklist.md](references/bootstrap-checklist.md) when you need
the full rollout sequence.
Read [adoption-gates.md](references/adoption-gates.md) before replacing an
existing memory workflow with this one.
Read [retrieval-benchmark-format.md](references/retrieval-benchmark-format.md)
when preparing cutover benchmarks.

### 4. Seed the memory layer deliberately

- Capture curated traces for active architecture, deployment, migrations,
  interface contracts, or incident-driven decisions.
- Use `git_backfill` only as advisory history, not as durable policy.
- Keep traces factual: problem, decision, alternatives, constraints, evidence,
  verification, outcome, open questions.
- Before adding another trace, inspect the current task's traces. Update an
  uncommitted trace when review changes the same decision; add a separate
  trace only for an independently useful decision or a committed-history change.

Example:

```bash
PYTHONPATH=.agents/context-graph/tools python -m repo_memory.capture \
  --repo-root . \
  --trace-id 2026-04-21-example \
  --title "Document expand/contract rollout rule" \
  --tags migrations,deploy,policy \
  --problem "Dual-version deploys lacked an explicit migration rule." \
  --decision "Adopt expand/contract migrations for dual-version windows." \
  --alternatives "Leave this implicit in code review only." \
  --constraints "Must support rollback and mixed-version traffic." \
  --evidence "Deploy workflow, migration incidents, review notes." \
  --verification "Reviewed current deploy flow and migration order." \
  --outcome "Rule is now searchable in repo-local memory." \
  --open-questions "Whether to add CI enforcement."
```

### 5. Promote durable rules into policies

When a trace or doc reveals a stable repository rule, create a policy:

```bash
PYTHONPATH=.agents/context-graph/tools python -m repo_memory.promote_policy \
  --repo-root . \
  --trace-id 2026-04-21-example \
  --policy-name expand_contract_migrations \
  --rule "Do not ship destructive schema cleanup in the same release as new code." \
  --rule "Use additive expand steps first and contract later." \
  --check "Migration review includes explicit compatibility note."
```

Use [policy-promotion.md](references/policy-promotion.md) to decide whether a
decision belongs in `traces/` or `policies/`.

### 6. Wire retrieval into `AGENTS.md`

Add a short workflow that tells future agents to:

1. Read `AGENTS.md`.
2. For substantial tasks, start retrieval with
   `PYTHONPATH=.agents/context-graph/tools python -m repo_memory.query --text ... --paths ... --include-policies`.
3. Load at most five relevant traces or policies before reading source files.
4. If retrieval looks weak or the task changes memory workflow behavior, run
   `PYTHONPATH=.agents/context-graph/tools python -m repo_memory.shadow_mode --task-summary ... --query ... --paths ...`.
5. If a legacy workflow exists, keep it as a temporary fallback until shadow
   results justify removing it.
6. Capture new traces after material changes.
7. Promote repeatable rules into `policies/`.
8. After capture or review fixes and before commit, reconcile current-task
   traces with the final diff using `repo_memory.review_changes`, then validate.
   Carry this step into the repository's `AGENTS.md`; global instructions alone
   do not update an existing repository workflow.

### 7. Validate before relying on it

Run:

```bash
PYTHONPATH=.agents/context-graph/tools python -m repo_memory.validate --repo-root .
PYTHONPATH=.agents/context-graph/tools python -m repo_memory.query --repo-root . \
  --text "deploy migrations rollback" --paths AGENTS.md --include-policies
```

If historical coverage matters, backfill selectively:

```bash
PYTHONPATH=.agents/context-graph/tools python -m repo_memory.backfill_git --repo-root . --limit 50
```

## Operating Rules

- Prefer a few high-signal curated traces over many noisy backfilled ones.
- Promote only durable, repeatable rules into `policies/`.
- Keep policy text short, normative, and easy to reuse in reviews.
- Do not treat the memory layer as a dumping ground for changelog entries.
- Consolidate current-task drafts; preserve committed decision history with
  explicit supersession. Do not delete traces solely for sharing paths or tags.
- Preserve local repo conventions when upgrading an existing setup.
- Keep migrations reversible: add `.agents/context-graph/tools/repo_memory`
  before changing `AGENTS.md`, and do not delete a legacy memory toolkit until
  the new workflow has proven itself.
- Treat `shadow_mode` as a diagnostic or adoption gate. Day-to-day operation
  should use `repo_memory.query` directly once the repo trusts the toolkit.

## Files

- `scripts/bootstrap_repo_memory.py`: install the repo-local toolkit.
- `scripts/evaluate_retrieval_benchmark.py`: compare baseline trace-only
  retrieval against the proposed trace+policy workflow.
- `scripts/templates/repo_memory/`: templates copied into the target repo.
- `scripts/templates/repo_memory/review_changes.py`: inventory changed traces
  and exact-decision duplicate candidates without editing files.
- `references/trace-maintenance.md`: reconcile task drafts after review and
  verify memory before commit.
- `scripts/templates/repo_memory/shadow_mode.py`: record retrieval diagnostics
  and append a JSONL shadow-mode record.
- `references/bootstrap-checklist.md`: rollout sequence and validation bar.
- `references/adoption-gates.md`: success criteria for shadow mode and cutover.
- `references/retrieval-benchmark-format.md`: benchmark file structure and
  metric meanings.
- `references/policy-promotion.md`: criteria for trace vs policy decisions.
