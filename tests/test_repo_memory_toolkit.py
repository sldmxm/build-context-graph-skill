import json
import sys
from pathlib import Path

TOOLKIT_ROOT = (
    Path(__file__).resolve().parents[1] / 'scripts' / 'templates'
)
sys.path.insert(0, str(TOOLKIT_ROOT))

from repo_memory import query, shadow_mode  # noqa: E402
from repo_memory.shared import (  # noqa: E402
    ensure_context_graph_scaffold,
    format_trace_document,
    parse_csv_argument,
    parse_frontmatter,
    traces_root,
)


def _write_trace(
    repo_root: Path,
    *,
    trace_id: str,
    title: str,
    paths: list[str],
    tags: list[str],
    decision: str,
    created_at: str = '2026-05-08T10:00:00+00:00',
) -> Path:
    ensure_context_graph_scaffold(repo_root)
    document = format_trace_document(
        metadata={
            'trace_id': trace_id,
            'created_at': created_at,
            'source_type': 'task_capture',
            'confidence': 'high',
            'status': 'active',
            'paths': paths,
            'tags': tags,
            'commit_shas': [],
            'supersedes': [],
        },
        title=title,
        sections={
            'Problem': f'Problem for {title}.',
            'Decision': decision,
            'Alternatives': 'Keep the previous behavior.',
            'Constraints': 'Keep the toolkit portable.',
            'Evidence': 'Synthetic fixture trace.',
            'Verification': 'Covered by toolkit tests.',
            'Outcome': 'Trace is queryable.',
            'Open Questions': 'None.',
        },
    )
    trace_path = traces_root(repo_root) / f'{trace_id}.md'
    trace_path.write_text(document, encoding='utf-8')
    return trace_path


def test_query_args_accept_multiple_path_tokens():
    args = query._parse_args(
        [
            '--text',
            'mobile parity',
            '--paths',
            'apps/web',
            'apps/mobile',
            '--include-policies',
        ]
    )

    assert args.paths == ['apps/web', 'apps/mobile']


def test_parse_csv_argument_accepts_common_path_forms():
    assert parse_csv_argument(
        ['apps/web', 'apps/mobile', 'packages/shared']
    ) == [
        'apps/web',
        'apps/mobile',
        'packages/shared',
    ]
    assert parse_csv_argument('apps/web apps/mobile') == [
        'apps/web',
        'apps/mobile',
    ]
    assert parse_csv_argument('apps/web,apps/mobile') == [
        'apps/web',
        'apps/mobile',
    ]


def test_parse_frontmatter_accepts_prettier_multiline_arrays():
    metadata, body = parse_frontmatter(
        """---
trace_id: prettier-trace
created_at: 2026-04-26T10:00:00+00:00
source_type: task_capture
confidence: medium
status: active
paths:
  [
    "app/main.py",
    "tests/test_main.py",
  ]
tags:
  [
    "formatting",
    "frontmatter",
  ]
commit_shas:
  [
    "abc1234",
  ]
supersedes:
  []
---
# Prettier trace
"""
    )

    assert metadata['trace_id'] == 'prettier-trace'
    assert metadata['paths'] == ['app/main.py', 'tests/test_main.py']
    assert metadata['tags'] == ['formatting', 'frontmatter']
    assert metadata['commit_shas'] == ['abc1234']
    assert metadata['supersedes'] == []
    assert body.startswith('# Prettier trace')


def test_query_ranks_specific_trace_above_broad_trace(tmp_path: Path):
    _write_trace(
        tmp_path,
        trace_id='specific-auth-locale',
        title='Auth login locale write rule',
        paths=['app/core/services/auth_service.py'],
        tags=['auth', 'locale'],
        decision='Write locale only for newly created auth users.',
    )
    _write_trace(
        tmp_path,
        trace_id='broad-locale-rollout',
        title='Locale rollout',
        paths=[
            'app/api',
            'app/core',
            'app/db',
            'docs',
            'tests',
        ],
        tags=['locale'],
        decision='Broad locale rollout background.',
        created_at='2026-05-08T11:00:00+00:00',
    )

    exit_code = query.main(
        [
            '--repo-root',
            str(tmp_path),
            '--text',
            'Should auth login write locale for every login or only new users?',
            '--paths',
            'app/core/services/auth_service.py',
        ]
    )

    assert exit_code == 0


def test_ranker_prefers_path_and_query_specific_trace(tmp_path: Path):
    specific = _write_trace(
        tmp_path,
        trace_id='specific-auth-locale',
        title='Auth login locale write rule',
        paths=['app/core/services/auth_service.py'],
        tags=['auth', 'locale'],
        decision='Write locale only for newly created auth users.',
    )
    broad = _write_trace(
        tmp_path,
        trace_id='broad-locale-rollout',
        title='Locale rollout',
        paths=['app/api', 'app/core', 'app/db', 'docs', 'tests'],
        tags=['locale'],
        decision='Broad locale rollout background.',
        created_at='2026-05-08T11:00:00+00:00',
    )

    documents = [
        query.load_trace_document(path)
        for path in [
            specific,
            broad,
        ]
    ]
    ranked = query.rank_trace_documents(
        documents=documents,
        query='auth login write locale newly created users',
        query_paths=['app/core/services/auth_service.py'],
        limit=5,
    )

    assert ranked[0].document.metadata['trace_id'] == 'specific-auth-locale'


def test_shadow_mode_writes_jsonl_log(tmp_path: Path):
    _write_trace(
        tmp_path,
        trace_id='memory-layout',
        title='Move repo memory under agents',
        paths=['.agents/context-graph/tools/repo_memory'],
        tags=['memory', 'tooling'],
        decision='Run repo memory from the .agents tools directory.',
    )
    log_path = tmp_path / 'shadow_mode_log.jsonl'

    exit_code = shadow_mode.main(
        [
            '--repo-root',
            str(tmp_path),
            '--task-summary',
            'Inspect memory layout',
            '--query',
            'repo memory tools under agents',
            '--paths',
            '.agents/context-graph/tools/repo_memory',
            '--decision',
            'proposed',
            '--log-path',
            str(log_path),
        ]
    )

    assert exit_code == 0
    payload = json.loads(log_path.read_text(encoding='utf-8').strip())
    assert payload['baseline'] == {
        'top_trace_ids': [],
        'results': [],
    }
    assert payload['proposed']['top_trace_ids'] == ['memory-layout']
