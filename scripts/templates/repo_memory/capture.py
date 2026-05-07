import argparse
from pathlib import Path

from scripts.repo_memory.shared import (
    current_head_sha,
    current_timestamp,
    discover_changed_paths,
    ensure_context_graph_scaffold,
    format_trace_document,
    parse_csv_argument,
    traces_root,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Capture a task trace into the local context graph.',
    )
    parser.add_argument('--repo-root', type=Path, default=Path.cwd())
    parser.add_argument('--trace-id', required=True)
    parser.add_argument('--title', required=True)
    parser.add_argument('--tags', required=True)
    parser.add_argument('--problem', required=True)
    parser.add_argument('--decision', required=True)
    parser.add_argument('--alternatives', required=True)
    parser.add_argument('--constraints', required=True)
    parser.add_argument('--evidence', required=True)
    parser.add_argument('--verification', required=True)
    parser.add_argument('--outcome', required=True)
    parser.add_argument('--open-questions', required=True)
    parser.add_argument('--paths', default=None)
    parser.add_argument('--commit-shas', default=None)
    parser.add_argument('--supersedes', default=None)
    parser.add_argument(
        '--confidence',
        choices=('low', 'medium', 'high'),
        default='medium',
    )
    parser.add_argument(
        '--status',
        choices=('active', 'deprecated', 'superseded'),
        default='active',
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    ensure_context_graph_scaffold(args.repo_root)

    paths = parse_csv_argument(args.paths)
    if not paths:
        paths = discover_changed_paths(args.repo_root)
    if not paths:
        raise ValueError('No paths provided and no changed paths detected.')

    commit_shas = parse_csv_argument(args.commit_shas)
    if not commit_shas:
        head_sha = current_head_sha(args.repo_root)
        if head_sha:
            commit_shas = [head_sha]

    metadata = {
        'trace_id': args.trace_id,
        'created_at': current_timestamp(),
        'source_type': 'task_capture',
        'confidence': args.confidence,
        'status': args.status,
        'paths': paths,
        'tags': parse_csv_argument(args.tags),
        'commit_shas': commit_shas,
        'supersedes': parse_csv_argument(args.supersedes),
    }
    sections = {
        'Problem': args.problem,
        'Decision': args.decision,
        'Alternatives': args.alternatives,
        'Constraints': args.constraints,
        'Evidence': args.evidence,
        'Verification': args.verification,
        'Outcome': args.outcome,
        'Open Questions': args.open_questions,
    }
    filename = f'{args.trace_id}.md'
    path = traces_root(args.repo_root) / filename
    if path.exists():
        raise FileExistsError(f'Trace already exists: {path}')

    path.write_text(
        format_trace_document(
            metadata=metadata,
            title=args.title,
            sections=sections,
        ),
        encoding='utf-8',
    )
    print(path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
