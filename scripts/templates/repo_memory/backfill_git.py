import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from scripts.repo_memory.shared import (
    LOW_SIGNAL_SUBJECTS,
    current_timestamp,
    ensure_context_graph_scaffold,
    format_trace_document,
    manifest_path,
)


@dataclass(slots=True)
class CommitRecord:
    sha: str
    parents: list[str]
    subject: str
    body: str
    committed_at: str
    paths: list[str]
    diff_summary: str

    @property
    def is_merge(self) -> bool:
        return len(self.parents) > 1

    @property
    def short_sha(self) -> str:
        return self.sha[:7]

    @property
    def is_low_signal(self) -> bool:
        subject = self.subject.strip().lower()
        return subject in LOW_SIGNAL_SUBJECTS or len(subject.split()) <= 1


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Backfill advisory traces from local git history.',
    )
    parser.add_argument('--repo-root', type=Path, default=Path.cwd())
    parser.add_argument('--limit', type=int, default=100)
    parser.add_argument('--rev-range', default=None)
    args = parser.parse_args(argv)
    if args.limit <= 0:
        raise ValueError('--limit must be > 0')
    return args


def _git_lines(repo_root: Path, *args: str) -> list[str]:
    result = subprocess.run(
        ['git', *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.splitlines()


def _load_manifest(repo_root: Path) -> dict:
    return json.loads(manifest_path(repo_root).read_text(encoding='utf-8'))


def _write_manifest(repo_root: Path, payload: dict) -> None:
    manifest_path(repo_root).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )


def _collect_commits(
    repo_root: Path,
    *,
    limit: int,
    processed_commits: set[str],
    rev_range: str | None,
) -> list[CommitRecord]:
    log_command = [
        'git',
        'log',
        f'-n{limit}',
        '--format=%H%x1f%P%x1f%cI%x1f%s%x1f%b%x1e',
    ]
    if rev_range:
        log_command.append(rev_range)
    log_output = subprocess.run(
        log_command,
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    records: list[CommitRecord] = []
    for raw_entry in log_output.split('\x1e'):
        entry = raw_entry.strip()
        if not entry:
            continue
        parts = entry.split('\x1f', 4)
        if len(parts) < 5:
            parts.extend([''] * (5 - len(parts)))
        sha, parents, committed_at, subject, body = parts
        if sha in processed_commits:
            continue
        paths = _git_lines(
            repo_root,
            'show',
            '--name-only',
            '--format=',
            sha,
        )
        normalized_paths = [path.strip() for path in paths if path.strip()]
        if not normalized_paths:
            continue
        diff_summary = '\n'.join(
            _git_lines(repo_root, 'show', '--shortstat', '--format=', sha)
        ).strip()
        record = CommitRecord(
            sha=sha,
            parents=[parent for parent in parents.split() if parent],
            subject=subject.strip(),
            body=body.strip(),
            committed_at=committed_at.strip(),
            paths=normalized_paths,
            diff_summary=diff_summary,
        )
        if record.is_merge and not record.body.strip():
            continue
        records.append(record)
    return records


def _extract_tags(
    record: CommitRecord,
    *,
    rev_range: str | None,
) -> list[str]:
    tags = set()
    for path in record.paths[:10]:
        parts = [
            part for part in Path(path).parts if part not in {'app', 'tests'}
        ]
        if parts:
            tags.add(parts[0].lower())
        stem = Path(path).stem.replace('_', '-')
        if stem and stem not in {'__init__'}:
            tags.add(stem.lower())
    for token in record.subject.lower().replace(':', ' ').split():
        token = token.strip()
        if len(token) > 2:
            tags.add(token)
    if record.is_low_signal:
        tags.add('low-signal')
    if rev_range:
        tags.add('premerge-candidate')
    return sorted(tags)[:8]


def _build_trace_filename(record: CommitRecord) -> str:
    return f'git-backfill-{record.short_sha}.md'


def _build_trace_text(
    record: CommitRecord,
    *,
    rev_range: str | None,
) -> str:
    constraints = (
        'This trace was reconstructed from commit metadata only. Treat it as '
        'advisory until superseded by a task_capture or manual_curated trace.'
    )
    if rev_range:
        constraints = (
            f'{constraints} Imported from non-merged git range "{rev_range}" '
            'to pre-seed likely incoming changes.'
        )
    outcome = 'Recorded as advisory repository history.'
    if record.is_low_signal:
        outcome = (
            'Recorded as low-signal historical record. Validate against code '
            'and newer traces before reuse.'
        )

    sections = {
        'Problem': (
            f'Historical change reconstructed from commit '
            f'"{record.subject or record.short_sha}".'
        ),
        'Decision': (
            record.body
            or (
                'Git history indicates this change introduced: '
                f'{record.subject}.'
            )
        ),
        'Alternatives': (
            'Historical alternatives are unknown from git-only backfill.'
        ),
        'Constraints': constraints,
        'Evidence': (
            'Historical reconstruction from local git metadata.\n'
            f'Commit: {record.sha}\n'
            f'Files: {", ".join(record.paths[:12])}\n'
            f'Diff summary: {record.diff_summary or "unavailable"}'
        ),
        'Verification': (
            'Backfill from git history only. No direct runtime verification '
            'captured in this trace.'
        ),
        'Outcome': outcome,
        'Open Questions': (
            'What product or architectural rationale sat behind this change?'
        ),
    }
    metadata = {
        'trace_id': f'git-backfill-{record.short_sha}',
        'created_at': record.committed_at or current_timestamp(),
        'source_type': 'git_backfill',
        'confidence': 'low',
        'status': 'active',
        'paths': record.paths[:20],
        'tags': _extract_tags(record, rev_range=rev_range),
        'commit_shas': [record.sha],
        'supersedes': [],
    }
    return format_trace_document(
        metadata=metadata,
        title=record.subject or f'Historical change {record.short_sha}',
        sections=sections,
    )


def run_backfill(
    *,
    repo_root: Path,
    output_root: Path | None = None,
    limit: int,
    rev_range: str | None = None,
) -> dict[str, object]:
    ensure_context_graph_scaffold(repo_root)
    graph_root = output_root or repo_root / '.agents' / 'context-graph'
    graph_root.mkdir(parents=True, exist_ok=True)
    traces_dir = graph_root / 'traces'
    traces_dir.mkdir(parents=True, exist_ok=True)

    manifest = _load_manifest(repo_root)
    processed_commits = set(manifest['backfill']['processed_commits'])
    records = _collect_commits(
        repo_root,
        limit=limit,
        processed_commits=processed_commits,
        rev_range=rev_range,
    )

    created_trace_ids: list[str] = []
    for record in records:
        filename = _build_trace_filename(record)
        trace_path = traces_dir / filename
        if trace_path.exists():
            continue
        trace_path.write_text(
            _build_trace_text(record, rev_range=rev_range),
            encoding='utf-8',
        )
        created_trace_ids.append(filename)
        processed_commits.add(record.sha)

    manifest['backfill']['processed_commits'] = sorted(processed_commits)
    manifest['backfill']['last_run_at'] = current_timestamp()
    manifest['backfill']['last_limit'] = limit
    manifest['backfill']['last_rev_range'] = rev_range
    _write_manifest(repo_root, manifest)

    return {
        'created_total': len(created_trace_ids),
        'created_trace_ids': created_trace_ids,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = run_backfill(
        repo_root=args.repo_root,
        limit=args.limit,
        rev_range=args.rev_range,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
