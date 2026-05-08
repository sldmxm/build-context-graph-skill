import argparse
import json
import re
from pathlib import Path

from repo_memory.shared import (
    context_graph_root,
    load_trace_document,
    policies_root,
    traces_root,
)

STABLE_RULE_PATTERNS = (
    ('must', 6.0),
    ('must not', 6.0),
    ('do not', 6.0),
    ('never', 5.0),
    ('always', 4.0),
    ('required', 4.0),
    ('policy', 5.0),
    ('runbook', 4.0),
    ('backward-compatible', 4.0),
    ('expand/contract', 4.0),
)
SCAN_GLOBS = (
    'AGENTS.md',
    'README.md',
    'docs/**/*.md',
    '.github/workflows/**/*.yml',
    '.github/workflows/**/*.yaml',
    'infra/**/*.sh',
    'infra/**/*.md',
    'alembic/**/*.py',
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Audit a repository for context-graph coverage gaps.',
    )
    parser.add_argument('--repo-root', type=Path, default=Path.cwd())
    parser.add_argument('--limit', type=int, default=10)
    return parser.parse_args(argv)


def _unique_paths(repo_root: Path) -> list[Path]:
    seen: set[Path] = set()
    paths: list[Path] = []
    for pattern in SCAN_GLOBS:
        for path in repo_root.glob(pattern):
            if (
                not path.is_file()
                or '.agents/context-graph' in path.as_posix()
                or path in seen
            ):
                continue
            seen.add(path)
            paths.append(path)
    return sorted(paths)


def _first_heading_or_name(path: Path, text: str) -> str:
    match = re.search(r'^# (.+)$', text, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return path.name


def _score_policy_candidate(path: Path, text: str) -> tuple[float, list[str]]:
    lower = text.lower()
    score = 0.0
    reasons: list[str] = []
    if path.name == 'AGENTS.md':
        score += 10.0
        reasons.append('AGENTS.md often contains durable workflow rules.')
    if 'runbook' in path.name.lower():
        score += 4.0
        reasons.append('Filename suggests operational guidance.')
    if path.parts and path.parts[0] in {'docs', 'infra'}:
        score += 2.0
        reasons.append('Documentation or infra file.')
    for pattern, weight in STABLE_RULE_PATTERNS:
        if pattern in lower:
            score += weight
            reasons.append(f'Contains "{pattern}".')
    if 'verification checklist' in lower:
        score += 3.0
        reasons.append('Contains a verification checklist.')
    if 'rollback' in lower or 'incident' in lower:
        score += 2.0
        reasons.append('Mentions failure-handling or rollback behavior.')
    return score, reasons


def _excerpt(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(
            pattern in stripped.lower() for pattern, _ in STABLE_RULE_PATTERNS
        ):
            return stripped[:220]
    return text.strip().splitlines()[0][:220] if text.strip() else ''


def _policy_candidates(repo_root: Path, limit: int) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for path in _unique_paths(repo_root):
        text = path.read_text(encoding='utf-8', errors='ignore')
        score, reasons = _score_policy_candidate(path, text)
        if score <= 0:
            continue
        candidates.append(
            {
                'path': str(path.relative_to(repo_root)),
                'title': _first_heading_or_name(path, text),
                'score': score,
                'reasons': reasons[:4],
                'excerpt': _excerpt(text),
            }
        )
    return sorted(
        candidates,
        key=lambda item: (
            float(item['score']),
            str(item['path']),
        ),
        reverse=True,
    )[:limit]


def _promotion_candidates(
    repo_root: Path,
    limit: int,
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for path in sorted(traces_root(repo_root).glob('*.md')):
        document = load_trace_document(path)
        if document.metadata['source_type'] == 'git_backfill':
            continue
        text = ' '.join(document.sections.values()).lower()
        reasons: list[str] = []
        score = 0.0
        if 'durable' in text or 'stable' in text:
            score += 6.0
            reasons.append(
                'Trace text already frames the decision as durable.'
            )
        if 'policy' in text:
            score += 5.0
            reasons.append('Trace text already mentions policy.')
        if any(
            str(item).startswith('.agents/context-graph/policies/')
            for item in document.metadata['paths']
        ):
            score += 10.0
            reasons.append('Trace already references a policy path.')
        if score <= 0:
            continue
        candidates.append(
            {
                'trace_id': document.metadata['trace_id'],
                'title': document.title,
                'score': score,
                'path': str(path.relative_to(repo_root)),
                'reasons': reasons,
            }
        )
    return sorted(
        candidates,
        key=lambda item: (
            float(item['score']),
            str(item['trace_id']),
        ),
        reverse=True,
    )[:limit]


def _agents_snippet() -> str:
    return (
        '1. Read AGENTS.md.\n'
        '2. Query `.agents/context-graph` with '
        '`PYTHONPATH=.agents/context-graph/tools python -m '
        'repo_memory.query --text ... --paths ... --include-policies`.\n'
        '3. Load at most five relevant traces or policies.\n'
        '4. Only then open source files.\n'
        '5. After material changes, capture a trace with '
        '`PYTHONPATH=.agents/context-graph/tools python -m '
        'repo_memory.capture ...`.\n'
        '6. If a rule is stable and repeatable, promote it with '
        '`PYTHONPATH=.agents/context-graph/tools python -m '
        'repo_memory.promote_policy ...`.'
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    graph_root = context_graph_root(args.repo_root)
    report = {
        'repo_root': str(args.repo_root),
        'context_graph_exists': graph_root.exists(),
        'trace_count': len(list(traces_root(args.repo_root).glob('*.md'))),
        'policy_count': len(
            [
                path
                for path in policies_root(args.repo_root).glob('*.md')
                if path.name != 'README.md'
            ]
        )
        if policies_root(args.repo_root).exists()
        else 0,
        'policy_candidates': _policy_candidates(args.repo_root, args.limit),
        'promotion_candidates': _promotion_candidates(
            args.repo_root,
            args.limit,
        )
        if traces_root(args.repo_root).exists()
        else [],
        'agents_snippet': _agents_snippet(),
        'next_actions': [
            'Bootstrap the scaffold if `.agents/context-graph` is absent.',
            'Capture curated traces for active architecture decisions.',
            'Promote durable rules from traces or docs into `policies/`.',
        ],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
