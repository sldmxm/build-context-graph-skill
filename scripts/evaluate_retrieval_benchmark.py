#!/usr/bin/env python3
import argparse
import importlib.util
import json
import re
from pathlib import Path
from typing import Any


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Evaluate retrieval cutover readiness on a benchmark set.',
    )
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument('--benchmark', type=Path, required=True)
    parser.add_argument('--limit', type=int, default=5)
    return parser.parse_args(argv)


def _load_module(module_path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f'Cannot load module from {module_path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_agent_memory_shared(repo_root: Path):
    module_path = repo_root / 'scripts' / 'agent_memory' / 'shared.py'
    if not module_path.exists():
        raise FileNotFoundError(
            f'Baseline agent_memory shared module not found: {module_path}'
        )
    return _load_module(module_path, 'benchmark_agent_memory_shared')


def _load_proposed_shared():
    module_path = (
        Path(__file__).resolve().parent
        / 'templates'
        / 'repo_memory'
        / 'shared.py'
    )
    return _load_module(module_path, 'benchmark_proposed_shared')


def _tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r'[a-z0-9][a-z0-9_-]*', text.lower())
        if len(token) > 1
    }


def _load_policy_candidates(repo_root: Path) -> list[tuple[Path, str, str]]:
    policies_root = repo_root / '.agents' / 'context-graph' / 'policies'
    candidates: list[tuple[Path, str, str]] = []
    if not policies_root.exists():
        return candidates
    for path in sorted(policies_root.glob('*.md')):
        if path.name == 'README.md':
            continue
        text = path.read_text(encoding='utf-8')
        match = re.search(r'^# (.+)$', text, re.MULTILINE)
        title = match.group(1).strip() if match else path.stem
        candidates.append((path, title, text))
    return candidates


def _rank_policies(
    *,
    repo_root: Path,
    query: str,
    limit: int,
) -> list[dict[str, Any]]:
    query_tokens = _tokenize(query)
    ranked: list[dict[str, Any]] = []
    for path, title, text in _load_policy_candidates(repo_root):
        text_tokens = _tokenize(f'{path.stem} {title} {text}')
        score = 2.0 * len(query_tokens & text_tokens)
        if 'policy' in path.stem:
            score += 1.0
        if score <= 0:
            continue
        ranked.append(
            {
                'policy_name': path.name,
                'title': title,
                'path': str(path),
                'score': score,
            }
        )
    return sorted(
        ranked,
        key=lambda item: (float(item['score']), str(item['path'])),
        reverse=True,
    )[:limit]


def _rank_traces(
    *,
    shared_module,
    repo_root: Path,
    query: str,
    query_paths: list[str],
    limit: int,
) -> list[dict[str, Any]]:
    traces_root = repo_root / '.agents' / 'context-graph' / 'traces'
    documents = [
        shared_module.load_trace_document(path)
        for path in sorted(traces_root.glob('*.md'))
    ]
    ranked = shared_module.rank_trace_documents(
        documents=documents,
        query=query,
        query_paths=query_paths,
        limit=limit,
    )
    return [
        {
            'trace_id': item.document.metadata['trace_id'],
            'title': item.document.title,
            'path': str(item.document.path),
            'score': item.score,
        }
        for item in ranked
    ]


def _index_ranks(
    items: list[dict[str, Any]],
    key: str,
) -> dict[str, int]:
    return {str(item[key]): index for index, item in enumerate(items, start=1)}


def _best_rank(
    expected_trace_ids: list[str],
    expected_policy_names: list[str],
    trace_ranks: dict[str, int],
    policy_ranks: dict[str, int],
) -> int | None:
    ranks = [
        trace_ranks[trace_id]
        for trace_id in expected_trace_ids
        if trace_id in trace_ranks
    ]
    ranks.extend(
        policy_ranks[policy_name]
        for policy_name in expected_policy_names
        if policy_name in policy_ranks
    )
    return min(ranks) if ranks else None


def _case_report(
    *,
    shared_module,
    repo_root: Path,
    case: dict[str, Any],
    limit: int,
) -> dict[str, Any]:
    query_paths = case.get('query_paths', [])
    expected_trace_ids = case.get('expected_trace_ids', [])
    expected_policy_names = case.get('expected_policy_names', [])

    baseline_traces = _rank_traces(
        shared_module=shared_module,
        repo_root=repo_root,
        query=case['query'],
        query_paths=query_paths,
        limit=limit,
    )
    proposed_traces = baseline_traces
    proposed_policies = _rank_policies(
        repo_root=repo_root,
        query=case['query'],
        limit=limit,
    )

    baseline_trace_ranks = _index_ranks(baseline_traces, 'trace_id')
    proposed_trace_ranks = _index_ranks(proposed_traces, 'trace_id')
    proposed_policy_ranks = _index_ranks(proposed_policies, 'policy_name')

    baseline_best_rank = _best_rank(
        expected_trace_ids,
        [],
        baseline_trace_ranks,
        {},
    )
    proposed_best_rank = _best_rank(
        expected_trace_ids,
        expected_policy_names,
        proposed_trace_ranks,
        proposed_policy_ranks,
    )
    policy_best_rank = _best_rank(
        [],
        expected_policy_names,
        {},
        proposed_policy_ranks,
    )

    baseline_success = (
        baseline_best_rank is not None and baseline_best_rank <= limit
    )
    proposed_success = (
        proposed_best_rank is not None and proposed_best_rank <= limit
    )
    proposed_policy_success = (
        policy_best_rank is not None and policy_best_rank <= limit
    )

    return {
        'id': case['id'],
        'query': case['query'],
        'query_paths': query_paths,
        'expected_trace_ids': expected_trace_ids,
        'expected_policy_names': expected_policy_names,
        'baseline': {
            'success_at_k': baseline_success,
            'best_rank': baseline_best_rank,
            'top_trace_ids': [item['trace_id'] for item in baseline_traces],
        },
        'proposed': {
            'success_at_k': proposed_success,
            'best_rank': proposed_best_rank,
            'policy_success_at_k': proposed_policy_success,
            'top_trace_ids': [item['trace_id'] for item in proposed_traces],
            'top_policy_names': [
                item['policy_name'] for item in proposed_policies
            ],
        },
    }


def _metrics(cases: list[dict[str, Any]], limit: int) -> dict[str, Any]:
    total = len(cases)
    policy_cases = [case for case in cases if case['expected_policy_names']]
    baseline_successes = sum(
        1 for case in cases if case['baseline']['success_at_k']
    )
    proposed_successes = sum(
        1 for case in cases if case['proposed']['success_at_k']
    )
    baseline_top1 = sum(
        1 for case in cases if case['baseline']['best_rank'] == 1
    )
    proposed_top1 = sum(
        1 for case in cases if case['proposed']['best_rank'] == 1
    )
    proposed_policy_visibility = sum(
        1 for case in policy_cases if case['proposed']['policy_success_at_k']
    )

    regressions = [
        case['id']
        for case in cases
        if (
            case['baseline']['success_at_k']
            and not case['proposed']['success_at_k']
        )
    ]
    improvements = [
        case['id']
        for case in cases
        if (
            not case['baseline']['success_at_k']
            and case['proposed']['success_at_k']
        )
        or (
            case['expected_policy_names']
            and case['proposed']['policy_success_at_k']
        )
    ]

    return {
        'k': limit,
        'case_count': total,
        'policy_case_count': len(policy_cases),
        'baseline': {
            'recall_at_k': baseline_successes / total if total else 0.0,
            'top1_accuracy': baseline_top1 / total if total else 0.0,
            'policy_visibility_at_k': 0.0,
        },
        'proposed': {
            'recall_at_k': proposed_successes / total if total else 0.0,
            'top1_accuracy': proposed_top1 / total if total else 0.0,
            'policy_visibility_at_k': (
                proposed_policy_visibility / len(policy_cases)
                if policy_cases
                else 0.0
            ),
        },
        'regressions': regressions,
        'improvements': sorted(set(improvements)),
    }


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    repo_root = args.repo_root.resolve()
    benchmark_path = args.benchmark.resolve()
    payload = json.loads(benchmark_path.read_text(encoding='utf-8'))
    baseline_module = _load_agent_memory_shared(repo_root)
    proposed_module = _load_proposed_shared()

    cases = [
        _case_report(
            shared_module=baseline_module,
            repo_root=repo_root,
            case=case,
            limit=args.limit,
        )
        for case in payload['cases']
    ]
    for case_report, raw_case in zip(cases, payload['cases'], strict=False):
        proposed_traces = _rank_traces(
            shared_module=proposed_module,
            repo_root=repo_root,
            query=raw_case['query'],
            query_paths=raw_case.get('query_paths', []),
            limit=args.limit,
        )
        proposed_trace_ranks = _index_ranks(proposed_traces, 'trace_id')
        proposed_policy_ranks = _index_ranks(
            _rank_policies(
                repo_root=repo_root,
                query=raw_case['query'],
                limit=args.limit,
            ),
            'policy_name',
        )
        proposed_best_rank = _best_rank(
            raw_case.get('expected_trace_ids', []),
            raw_case.get('expected_policy_names', []),
            proposed_trace_ranks,
            proposed_policy_ranks,
        )
        policy_best_rank = _best_rank(
            [],
            raw_case.get('expected_policy_names', []),
            {},
            proposed_policy_ranks,
        )
        case_report['proposed'] = {
            'success_at_k': (
                proposed_best_rank is not None
                and proposed_best_rank <= args.limit
            ),
            'best_rank': proposed_best_rank,
            'policy_success_at_k': (
                policy_best_rank is not None and policy_best_rank <= args.limit
            ),
            'top_trace_ids': [item['trace_id'] for item in proposed_traces],
            'top_policy_names': list(proposed_policy_ranks.keys()),
        }
    report = {
        'benchmark_name': payload.get('name', benchmark_path.stem),
        'description': payload.get('description', ''),
        'metrics': _metrics(cases, args.limit),
        'cases': cases,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
