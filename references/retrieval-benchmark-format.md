# Retrieval Benchmark Format

Store benchmark cases as JSON.

## Top-Level Shape

```json
{
  "name": "repo-retrieval-cutover",
  "description": "Benchmark prompts for retrieval cutover decisions.",
  "cases": [
    {
      "id": "ab_deploy_migrations",
      "query": "What migration rules apply during staged deploys?",
      "query_paths": ["docs/deploy.md", "alembic"],
      "expected_trace_ids": ["2026-03-27-ab-deploy-docs-and-migration-policy"],
      "expected_policy_names": ["backward_compatible_migrations_for_ab_deploy.md"]
    }
  ]
}
```

## Field Meanings

- `id`: stable benchmark case identifier.
- `query`: the natural-language retrieval prompt.
- `query_paths`: optional path hints passed to trace ranking.
- `expected_trace_ids`: acceptable trace hits for the case.
- `expected_policy_names`: acceptable policy hits for the case.

Use empty arrays when a case intentionally expects only traces or only
policies.

## Metric Interpretation

The evaluator reports baseline and proposed metrics:

- `recall_at_k`: whether at least one expected artifact appears in the top `k`
  results.
- `top1_accuracy`: whether the best acceptable artifact is rank 1 in its
  result channel.
- `policy_visibility_at_k`: whether expected policies appear in the top `k`
  policy results.
- `regressions`: cases where baseline succeeds and proposed fails.
- `improvements`: cases where proposed succeeds and baseline fails, or where
  proposed exposes an expected policy that baseline cannot expose.

## Benchmark Design Rules

- Use real prompts that an engineer or agent would ask.
- Prefer 10-20 cases that cover stable policies and important traces.
- Include some policy-only cases; otherwise policy visibility is not tested.
- Keep expected artifacts narrow. Do not mark five loosely related traces as
  all acceptable unless they truly are interchangeable.
