import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

from repo_memory.shared import (
    context_graph_root,
    load_trace_document,
    parse_csv_argument,
    rank_trace_documents,
    tokenize,
    traces_root,
)


@dataclass(slots=True)
class RankedPolicy:
    path: Path
    title: str
    score: float


def _policies_root(repo_root: Path) -> Path:
    return context_graph_root(repo_root) / 'policies'


def _load_policy_candidates(repo_root: Path) -> list[tuple[Path, str, str]]:
    candidates: list[tuple[Path, str, str]] = []
    for path in sorted(_policies_root(repo_root).glob('*.md')):
        if path.name == 'README.md':
            continue
        text = path.read_text(encoding='utf-8')
        title_match = re.search(r'^# (.+)$', text, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else path.stem
        candidates.append((path, title, text))
    return candidates


def _rank_policies(
    *,
    repo_root: Path,
    query: str,
    limit: int,
) -> list[RankedPolicy]:
    query_tokens = tokenize(query)
    ranked: list[RankedPolicy] = []
    for path, title, text in _load_policy_candidates(repo_root):
        text_tokens = tokenize(f'{path.stem} {title} {text}')
        score = 2.0 * len(query_tokens & text_tokens)
        if 'policy' in path.stem:
            score += 1.0
        if score > 0:
            ranked.append(RankedPolicy(path=path, title=title, score=score))
    return sorted(
        ranked,
        key=lambda item: (item.score, item.path.name),
        reverse=True,
    )[:limit]


def rank_policy_documents(
    *,
    repo_root: Path,
    query: str,
    limit: int,
) -> list[dict[str, object]]:
    return [
        {
            'policy_name': item.path.name,
            'score': item.score,
            'path': str(item.path),
            'title': item.title,
        }
        for item in _rank_policies(
            repo_root=repo_root,
            query=query,
            limit=limit,
        )
    ]


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Query the repo-sidecar context graph.',
    )
    parser.add_argument('--repo-root', type=Path, default=Path.cwd())
    parser.add_argument('--text', required=True)
    parser.add_argument('--paths', nargs='*', default=None)
    parser.add_argument('--limit', type=int, default=5)
    parser.add_argument(
        '--include-policies',
        action='store_true',
        help='Include stable policy documents in the ranked results.',
    )
    args = parser.parse_args(argv)
    if args.limit <= 0:
        raise ValueError('--limit must be > 0')
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    documents = [
        load_trace_document(path)
        for path in sorted(traces_root(args.repo_root).glob('*.md'))
    ]
    ranked = rank_trace_documents(
        documents=documents,
        query=args.text,
        query_paths=parse_csv_argument(args.paths),
        limit=args.limit,
    )
    payload: dict[str, list[dict[str, object]]] = {
        'traces': [
            {
                'trace_id': item.document.metadata['trace_id'],
                'score': item.score,
                'path': str(item.document.path),
                'source_type': item.document.metadata['source_type'],
                'confidence': item.document.metadata['confidence'],
                'status': item.document.metadata['status'],
                'paths': item.document.metadata['paths'],
                'title': item.document.title,
            }
            for item in ranked
        ]
    }
    if args.include_policies:
        payload['policies'] = rank_policy_documents(
            repo_root=args.repo_root,
            query=args.text,
            limit=args.limit,
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
