import argparse
import json
import re
from pathlib import Path

from repo_memory.shared import (
    ensure_context_graph_scaffold,
    load_trace_document,
    policies_root,
    traces_root,
)


def _slugify(value: str) -> str:
    normalized = value.strip().lower()
    normalized = re.sub(r'[^a-z0-9]+', '_', normalized)
    return normalized.strip('_')


def _humanize_policy_name(value: str) -> str:
    words = [word for word in re.split(r'[_-]+', value.strip()) if word]
    return ' '.join(word.capitalize() for word in words)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Promote a task trace into a durable policy document.',
    )
    parser.add_argument('--repo-root', type=Path, default=Path.cwd())
    parser.add_argument('--trace-id', required=True)
    parser.add_argument('--policy-name', required=True)
    parser.add_argument('--title', default=None)
    parser.add_argument('--decision', default=None)
    parser.add_argument('--why', default=None)
    parser.add_argument('--rule', action='append', default=[])
    parser.add_argument('--implication', action='append', default=[])
    parser.add_argument('--check', action='append', default=[])
    parser.add_argument('--force', action='store_true')
    return parser.parse_args(argv)


def _split_lines(raw_text: str) -> list[str]:
    parts = re.split(r';|\n', raw_text)
    return [part.strip() for part in parts if part.strip()]


def _derive_rules(document) -> list[str]:
    decision_lines = _split_lines(document.sections['Decision'])
    constraints = _split_lines(document.sections['Constraints'])
    rules = decision_lines[:2] + constraints[:2]
    if not rules:
        return ['Preserve the decision recorded in the source trace.']
    return rules


def _derive_checks(document) -> list[str]:
    verification_lines = _split_lines(document.sections['Verification'])
    if verification_lines:
        return verification_lines[:4]
    return ['Review this policy against the current code paths and docs.']


def _render_policy(
    *,
    title: str,
    trace_id: str,
    decision: str,
    why: str,
    rules: list[str],
    implications: list[str],
    checks: list[str],
) -> str:
    lines = [
        f'# {title}',
        '',
        '## Status',
        'Stable policy.',
        '',
        '## Decision',
        decision.strip(),
        '',
        '## Why',
        why.strip(),
        '',
        '## Required Rules',
    ]
    lines.extend(f'- {rule}' for rule in rules)
    lines.extend(
        [
            '',
            '## Implications',
        ]
    )
    lines.extend(f'- {implication}' for implication in implications)
    lines.extend(
        [
            '',
            '## Verification Checklist',
        ]
    )
    lines.extend(f'- {check}' for check in checks)
    lines.extend(
        [
            '',
            '## Source',
            f'- Trace: `{trace_id}`',
            '',
        ]
    )
    return '\n'.join(lines)


def _update_policies_readme(repo_root: Path, policy_filename: str) -> bool:
    readme_path = policies_root(repo_root) / 'README.md'
    if not readme_path.exists():
        return False
    content = readme_path.read_text(encoding='utf-8')
    bullet = f'- `{policy_filename}`'
    if bullet in content:
        return False
    updated = content.rstrip() + f'\n{bullet}\n'
    readme_path.write_text(updated, encoding='utf-8')
    return True


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    ensure_context_graph_scaffold(args.repo_root)
    trace_path = traces_root(args.repo_root) / f'{args.trace_id}.md'
    if not trace_path.exists():
        raise FileNotFoundError(f'Trace not found: {trace_path}')

    document = load_trace_document(trace_path)
    title = args.title or _humanize_policy_name(args.policy_name)
    decision = args.decision or document.sections['Decision']
    why = args.why or document.sections['Problem']
    rules = args.rule or _derive_rules(document)
    implications = args.implication or _split_lines(
        document.sections['Constraints']
    )
    if not implications:
        implications = [
            'Keep this policy aligned with the repository workflow and docs.'
        ]
    checks = args.check or _derive_checks(document)

    policy_name = _slugify(args.policy_name)
    policy_filename = f'{policy_name}.md'
    policy_path = policies_root(args.repo_root) / policy_filename
    if policy_path.exists() and not args.force:
        raise FileExistsError(
            f'Policy already exists: {policy_path}. Use --force to overwrite.'
        )

    policy_path.write_text(
        _render_policy(
            title=title,
            trace_id=args.trace_id,
            decision=decision,
            why=why,
            rules=rules,
            implications=implications,
            checks=checks,
        ),
        encoding='utf-8',
    )
    readme_updated = _update_policies_readme(args.repo_root, policy_filename)
    payload = {
        'policy_path': str(policy_path),
        'readme_updated': readme_updated,
        'source_trace': args.trace_id,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
