# Policy Promotion

Use policies for stable repository rules. Use traces for decision records.

## Promote To Policy When

- the rule constrains future implementation choices;
- the rule applies across multiple files, reviews, or tasks;
- the rule is expected to stay valid beyond one change;
- the repo would regress if a future agent missed it;
- the same guidance keeps recurring in chat, docs, or review comments.

## Keep As Trace When

- the record is mainly historical context for one task;
- the tradeoff is still unsettled;
- the decision is specific to one migration, incident, or bugfix;
- the detail matters for evidence but should not constrain all future work.

## Good Policy Shape

- short title;
- one-paragraph decision;
- clear "why";
- 2-6 explicit rules;
- a small verification checklist.

## Anti-Patterns

- copying an entire task trace into `policies/`;
- writing aspirational policy that the repo does not actually follow;
- promoting temporary rollout notes or one-off cleanup steps;
- burying the real rule under narrative and historical detail.

## Example Split

Trace:
- "During the April rollout, we dual-wrote reads and writes across two tables."

Policy:
- "Schema changes must follow additive expand/contract rollout during
  dual-version deploy windows."
