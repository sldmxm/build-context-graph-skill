"""Read-only inventory for reconciling memory with the current change."""

import argparse
import json
import subprocess
from pathlib import Path

from repo_memory.shared import (
    TraceValidationError,
    load_trace_document,
    traces_root,
    validate_trace_document,
)


def _git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ['git', *args], cwd=repo_root, check=True,
        capture_output=True, text=True,
    )
    return result.stdout


def build_review_report(
    repo_root: Path, base: str | None = None,
) -> dict[str, object]:
    staged = set(_git(
        repo_root, 'diff', '--cached', '--name-only', '-z',
    ).split('\0')) - {''}
    unstaged = set(_git(
        repo_root, 'diff', '--name-only', '-z',
    ).split('\0')) - {''}
    untracked = set(_git(
        repo_root, 'ls-files', '--others', '--exclude-standard', '-z',
    ).split('\0')) - {''}
    committed = set()
    if base is not None:
        committed = set(_git(
            repo_root, 'diff', '--name-only', '-z', base, 'HEAD',
        ).split('\0')) - {''}
    changed = staged | unstaged | untracked | committed
    prefix = '.agents/context-graph/traces/'
    trace_paths = sorted(
        path for path in changed
        if path.startswith(prefix) and path.endswith('.md')
    )
    records = []
    errors = []
    decisions = {}
    for path in sorted(traces_root(repo_root).glob('*.md')):
        try:
            document = load_trace_document(path)
        except TraceValidationError:
            continue
        decision = ' '.join(document.sections['Decision'].split()).casefold()
        decisions.setdefault(decision, []).append(str(path.relative_to(
            repo_root,
        )))
    for relative in trace_paths:
        path = repo_root / relative
        record = {
            'path': relative,
            'staged': relative in staged,
            'unstaged': relative in unstaged,
            'untracked': relative in untracked,
            'committed_since_base': relative in committed,
            'deleted': not path.exists(),
        }
        if path.exists():
            try:
                document = load_trace_document(path)
                decision = ' '.join(
                    document.sections['Decision'].split(),
                ).casefold()
                record.update({
                    'trace_id': document.metadata['trace_id'],
                    'decision': document.sections['Decision'],
                    'verification': document.sections['Verification'],
                    'related_changed_paths': sorted(
                        set(document.metadata['paths']) & changed,
                    ),
                    'same_decision_candidates': [
                        item for item in decisions[decision]
                        if item != relative
                    ],
                })
            except TraceValidationError as exc:
                errors.append({'path': relative, 'version': 'worktree',
                               'error': str(exc)})
        if relative in staged:
            # Check the index too: a worktree repair may not be staged yet.
            indexed = subprocess.run(
                ['git', 'show', f':{relative}'], cwd=repo_root,
                check=False, capture_output=True, text=True,
            )
            if indexed.returncode == 0:
                try:
                    validate_trace_document(indexed.stdout)
                except TraceValidationError as exc:
                    errors.append({'path': relative, 'version': 'index',
                                   'error': str(exc)})
        records.append(record)
    return {
        'base': base,
        'changed_paths': sorted(changed),
        'traces': records,
        'errors': errors,
        'note': (
            'Candidates require semantic review against the final diff. '
            'This command does not edit files or the index.'
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, default=Path.cwd())
    parser.add_argument(
        '--base', help='Include committed task changes from this ref to HEAD.',
    )
    args = parser.parse_args(argv)
    report = build_review_report(args.repo_root.resolve(), args.base)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
