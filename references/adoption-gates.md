# Adoption Gates

Do not replace an existing repository memory workflow just because the new one
installs cleanly. Cut over only after it proves parity, better retrieval, and
safe day-to-day operation.

## Gate 1: Functional Parity

The new workflow must support all baseline operations that the current system
is relied on for:

- bootstrap scaffold creation;
- trace capture;
- trace validation;
- trace querying;
- git-history backfill if the repo uses it.

Pass this gate only if the new toolkit can operate on the current repository
without deleting or rewriting existing traces and policies.

## Gate 2: Retrieval Benchmark

Create a small evaluation set from the current repository before migration.
Use 10-20 realistic prompts. For each prompt, define the expected high-value
artifact(s): a trace, a policy, or both.

Examples:

- "expand/contract migrations during staged deploys"
- "shared validation answer semantics"
- "how to retrieve repo memory before opening source files"

Measure:

- `recall@5`: whether the expected artifact appears in the top 5 results;
- `top1 accuracy`: whether the best result is acceptable;
- `policy visibility`: whether stable policies are returned without manual grep.

Cutover threshold:

- no benchmark where the old workflow finds a critical artifact and the new
  workflow misses it entirely;
- at least 90% recall@5 on curated benchmark prompts;
- policy visibility strictly better than the old workflow.

## Gate 3: Workflow Cost

The new workflow must not be more expensive to use in normal tasks.

Track on 5-10 real tasks:

- time to first useful memory artifact;
- number of commands before the agent sees the right trace or policy;
- time to capture a new trace;
- time to promote a stable rule into policy.

Cutover threshold:

- median retrieval path is no worse than the current workflow;
- capture remains lightweight;
- promotion is materially easier than the current manual process.

## Gate 4: Shadow Mode

Run the new workflow in parallel with the old one on real repository tasks.
Do not remove the old instructions yet.

For each task, record:

- whether the new workflow surfaced the needed memory before code reading;
- whether a later review uncovered a missed durable rule;
- whether audit or policy promotion found something the old workflow would have
  left implicit.

Cutover threshold:

- at least 10 real tasks in shadow mode;
- zero cases where the old workflow had a critical memory artifact that the new
  workflow failed to surface;
- at least 2 tasks where the new workflow provided additional value through
  audit or policy promotion.

## Gate 5: Migration Safety

Before replacing the current system in the repo:

- keep all existing `.agents/context-graph/traces/*.md`;
- keep all existing `.agents/context-graph/policies/*.md`;
- migrate scripts by addition first, not deletion first;
- switch `AGENTS.md` instructions only after the new scripts are already
  present and proven.

Cutover threshold:

- migration diff is reversible;
- no existing trace or policy becomes unreadable;
- repository checks for the toolkit pass after migration.

## Final Cutover Rule

Retire the old workflow only when all five gates pass.

In practice that means:

1. The new toolkit has full functional parity.
2. The retrieval benchmark shows no critical regressions.
3. Real-task workflow cost is equal or lower.
4. Shadow mode shows no misses and some clear upside.
5. The repo migration is reversible and preserves history.

If any gate fails, keep the old workflow, patch the skill, and rerun the failed
gate instead of forcing migration.
