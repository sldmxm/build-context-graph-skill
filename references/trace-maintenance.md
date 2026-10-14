# Reconcile Current-Task Traces

Run this workflow before capture, after review fixes, and before commit when
the task changed engineering decisions. Avoid creating a trace for every
iteration of the same change.

## Inventory

From the target repository root:

```bash
PYTHONPATH=.agents/context-graph/tools python -m repo_memory.review_changes
```

The report includes staged, unstaged, untracked, and deleted trace paths. Use
`--base <task-start-ref>` when the task spans existing commits; choose the ref
from the task's actual history. Do not infer the scope from timestamps or scan
and rewrite the entire memory archive.

The tool checks changed worktree traces and staged trace content separately.
It lists exact Decision-text matches as candidates; it cannot determine
semantic duplication, contradictions, or missing coverage. Inspect those
against the final source diff, review findings, and verification results.

## Reconcile

- Update a current-task draft when review changes its decision, constraints,
  verification, or outcome. Remove claims about approaches that were abandoned.
- Merge drafts describing the same decision into one coherent trace. Keep
  distinct decisions separate even when their paths overlap.
- Delete an uncommitted draft only when its decision was abandoned or its
  useful evidence was preserved in another draft. Check incoming `supersedes`
  references and Markdown links before removing it. Preserve unrelated drafts
  and other contributors' work.
- For a committed decision that has changed, add a trace with `supersedes`
  pointing to the old trace ID. Where appropriate, mark the old trace
  `superseded`; do not silently rewrite the historical decision or delete it.
- If a changed decision affects a durable policy, update the policy too.
  A trace alone must not leave a contradictory rule in `policies/`.
- Add missing memory for decisions future agents need: constraints, rejected
  alternatives, compatibility boundaries, or incident evidence. Routine edits
  do not automatically require a trace.

## Verify

Use `capture` for new traces; it validates the rendered document before writing.
After manual edits, run:

```bash
PYTHONPATH=.agents/context-graph/tools python -m repo_memory.review_changes
PYTHONPATH=.agents/context-graph/tools python -m repo_memory.validate
```

Confirm trace claims match the checks actually run. Record failed or unavailable
verification honestly. Use `None identified.` when there are no open questions;
do not invent speculative follow-ups to fill a required section.

After staging, rerun the changed-trace review so a valid worktree does not mask
an invalid staged version. Structural validation in a commit hook is useful,
but it does not replace this semantic review. Never automatically stage files,
merge traces, or delete memory as a side effect of capture or validation.
