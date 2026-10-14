import json
import subprocess
import sys
from pathlib import Path

import pytest

TOOLKIT_ROOT = (
    Path(__file__).resolve().parents[1] / 'scripts' / 'templates'
)
sys.path.insert(0, str(TOOLKIT_ROOT))

from repo_memory import capture, query, review_changes, shadow_mode  # noqa: E402
from repo_memory.shared import (  # noqa: E402
    TraceValidationError,
    ensure_context_graph_scaffold,
    format_trace_document,
    parse_csv_argument,
    parse_frontmatter,
    traces_root,
    validate_trace_collection,
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


def test_capture_rejects_empty_section_before_writing(tmp_path: Path):
    argv = ['--repo-root', str(tmp_path), '--trace-id', 'empty-trace',
            '--title', 'Empty trace', '--tags', 'memory', '--paths', 'app.py']
    for flag in ('problem', 'decision', 'alternatives', 'constraints',
                 'evidence', 'verification', 'outcome', 'open-questions'):
        argv.extend([f'--{flag}', ' ' if flag == 'outcome' else 'Evidence.'])

    with pytest.raises(TraceValidationError, match='Outcome'):
        capture.main(argv)
    assert not (traces_root(tmp_path) / 'empty-trace.md').exists()


def _git(repo_root: Path, *args: str):
    return subprocess.run(
        ['git', *args], cwd=repo_root, check=True,
        capture_output=True, text=True,
    ).stdout


def test_review_reports_index_error_after_worktree_repair(tmp_path: Path):
    _git(tmp_path, 'init', '-q')
    path = _write_trace(
        tmp_path, trace_id='draft', title='Draft', paths=['app.py'],
        tags=['memory'], decision='Use explicit validation.',
    )
    valid = path.read_text(encoding='utf-8')
    path.write_text(valid.replace('\n## Open Questions\nNone.\n', '\n'),
                    encoding='utf-8')
    _git(tmp_path, 'add', str(path.relative_to(tmp_path)))
    path.write_text(valid, encoding='utf-8')
    index_before = _git(tmp_path, 'diff', '--cached')

    report = review_changes.build_review_report(tmp_path)

    assert report['errors'][0]['version'] == 'index'
    assert report['traces'][0]['staged']
    assert report['traces'][0]['unstaged']
    assert path.read_text(encoding='utf-8') == valid
    assert _git(tmp_path, 'diff', '--cached') == index_before


def test_review_includes_committed_task_and_duplicate_candidate(tmp_path):
    _git(tmp_path, 'init', '-q')
    first = _write_trace(
        tmp_path, trace_id='old', title='Earlier decision', paths=['app.py'],
        tags=['memory'], decision='Use explicit validation.',
    )
    _git(tmp_path, 'add', '.')
    _git(tmp_path, '-c', 'user.name=Test', '-c', 'user.email=test@test.invalid',
         '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'Seed')
    base = _git(tmp_path, 'rev-parse', 'HEAD').strip()
    second = _write_trace(
        tmp_path, trace_id='new', title='New draft', paths=['app.py'],
        tags=['memory'], decision='Use explicit validation.',
    )
    _git(tmp_path, 'add', '.')
    _git(tmp_path, '-c', 'user.name=Test', '-c', 'user.email=test@test.invalid',
         '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'Task')

    report = review_changes.build_review_report(tmp_path, base)

    assert report['errors'] == []
    assert report['traces'][0]['path'] == str(second.relative_to(tmp_path))
    assert report['traces'][0]['committed_since_base']
    assert report['traces'][0]['same_decision_candidates'] == [
        str(first.relative_to(tmp_path)),
    ]


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


def test_query_ranks_specific_trace_above_broad_trace(tmp_path: Path, capsys):
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
    assert json.loads(capsys.readouterr().out)['traces'][0]['trace_id'] == (
        'specific-auth-locale'
    )


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


def test_validate_trace_collection_reports_broken_trace_path(
    tmp_path: Path,
):
    trace_path = _write_trace(
        tmp_path,
        trace_id='broken-trace',
        title='Broken trace',
        paths=['AGENTS.md'],
        tags=['memory'],
        decision='This trace will be made invalid.',
    )
    trace_path.write_text(
        trace_path.read_text(encoding='utf-8').replace(
            '\n## Open Questions\nNone.\n',
            '\n',
        ),
        encoding='utf-8',
    )

    try:
        validate_trace_collection([trace_path], repo_root=tmp_path)
    except TraceValidationError as exc:
        message = str(exc)
    else:
        raise AssertionError('Expected TraceValidationError')

    assert str(trace_path) in message
    assert 'Missing or empty section: Open Questions' in message
