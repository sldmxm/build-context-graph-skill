import argparse
import json
from pathlib import Path
from typing import Any

from repo_memory.query import rank_policy_documents
from repo_memory.shared import (
    current_timestamp,
    load_trace_document,
    parse_csv_argument,
    rank_trace_documents,
    shadow_mode_log_path,
    traces_root,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            'Run repo-memory shadow mode and log retrieval comparison.'
        ),
    )
    parser.add_argument('--repo-root', type=Path, default=Path.cwd())
    parser.add_argument('--task-summary', required=True)
    parser.add_argument('--query', required=True)
    parser.add_argument('--paths', nargs='*', default=None)
    parser.add_argument('--limit', type=int, default=5)
    parser.add_argument(
        '--decision',
        choices=('proposed', 'undecided'),
        default='undecided',
        help='Whether proposed retrieval looked useful for this task.',
    )
    parser.add_argument(
        '--notes',
        default='',
        help='Optional one-line note about misses or retrieval quality.',
    )
    parser.add_argument(
        '--no-log',
        action='store_true',
        help='Print comparison only and do not append to the shadow log.',
    )
    parser.add_argument(
        '--log-path',
        type=Path,
        default=None,
        help='Override the default JSONL log path.',
    )
    args = parser.parse_args(argv)
    if args.limit <= 0:
        raise ValueError('--limit must be > 0')
    return args


def _rank_proposed_traces(
    *,
    repo_root: Path,
    query: str,
    query_paths: list[str],
    limit: int,
) -> list[dict[str, Any]]:
    documents = [
        load_trace_document(path)
        for path in sorted(traces_root(repo_root).glob('*.md'))
    ]
    ranked = rank_trace_documents(
        documents=documents,
        query=query,
        query_paths=query_paths,
        limit=limit,
    )
    return [
        {
            'trace_id': item.document.metadata['trace_id'],
            'score': item.score,
            'path': str(item.document.path),
            'title': item.document.title,
        }
        for item in ranked
    ]


def build_shadow_report(
    *,
    repo_root: Path,
    task_summary: str,
    query: str,
    query_paths: list[str],
    limit: int,
    decision: str,
    notes: str,
) -> dict[str, Any]:
    proposed_traces = _rank_proposed_traces(
        repo_root=repo_root,
        query=query,
        query_paths=query_paths,
        limit=limit,
    )
    proposed_policies = rank_policy_documents(
        repo_root=repo_root,
        query=query,
        limit=limit,
    )
    return {
        'timestamp': current_timestamp(),
        'task_summary': task_summary,
        'query': query,
        'query_paths': query_paths,
        'limit': limit,
        'decision': decision,
        'notes': notes,
        'baseline': {
            'top_trace_ids': [],
            'results': [],
        },
        'proposed': {
            'top_trace_ids': [item['trace_id'] for item in proposed_traces],
            'top_policy_names': [
                item['policy_name'] for item in proposed_policies
            ],
            'trace_results': proposed_traces,
            'policy_results': proposed_policies,
        },
    }


def _append_log(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + '\n')


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    query_paths = parse_csv_argument(args.paths)
    report = build_shadow_report(
        repo_root=args.repo_root,
        task_summary=args.task_summary,
        query=args.query,
        query_paths=query_paths,
        limit=args.limit,
        decision=args.decision,
        notes=args.notes,
    )
    if not args.no_log:
        log_path = args.log_path or shadow_mode_log_path(args.repo_root)
        _append_log(log_path, report)
        report['log_path'] = str(log_path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
