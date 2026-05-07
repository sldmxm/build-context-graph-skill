import ast
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

TRACE_SCHEMA_VERSION = 1
CONTEXT_GRAPH_DIR = Path('.agents') / 'context-graph'
REQUIRED_FRONTMATTER_KEYS = (
    'trace_id',
    'created_at',
    'source_type',
    'confidence',
    'status',
    'paths',
    'tags',
    'commit_shas',
    'supersedes',
)
REQUIRED_SECTIONS = (
    'Problem',
    'Decision',
    'Alternatives',
    'Constraints',
    'Evidence',
    'Verification',
    'Outcome',
    'Open Questions',
)
VALID_SOURCE_TYPES = {'git_backfill', 'task_capture', 'manual_curated'}
VALID_CONFIDENCE = {'low', 'medium', 'high'}
VALID_STATUS = {'active', 'deprecated', 'superseded'}
LOW_SIGNAL_SUBJECTS = {
    'wip',
    'fix',
    'tmp',
    'misc',
    'updates',
    'changes',
}

TRACE_SCHEMA_MARKDOWN = """# Trace Schema

Every trace uses YAML-style frontmatter with JSON array values where lists are
needed.

Required frontmatter keys:

- `trace_id`
- `created_at`
- `source_type`
- `confidence`
- `status`
- `paths`
- `tags`
- `commit_shas`
- `supersedes`

Allowed values:

- `source_type`: `git_backfill`, `task_capture`, `manual_curated`
- `confidence`: `low`, `medium`, `high`
- `status`: `active`, `deprecated`, `superseded`

Required sections:

- `Problem`
- `Decision`
- `Alternatives`
- `Constraints`
- `Evidence`
- `Verification`
- `Outcome`
- `Open Questions`
"""

TRACE_TEMPLATE_MARKDOWN = """---
trace_id: example-trace-id
created_at: 2026-03-10T10:00:00+00:00
source_type: task_capture
confidence: medium
status: active
paths: ["app/main.py"]
tags: ["startup", "harness"]
commit_shas: []
supersedes: []
---
# Example trace title

## Problem
State the engineering problem.

## Decision
Describe what was decided.

## Alternatives
List rejected alternatives.

## Constraints
List repo or runtime constraints.

## Evidence
Cite files, commits, docs, or incidents.

## Verification
List tests or checks that verify the decision.

## Outcome
Describe the result or current state.

## Open Questions
Capture remaining uncertainty.
"""

CONTEXT_GRAPH_README = """# Context Graph

Use this directory as the repo-local memory layer for engineering decisions.

Retrieval policy:

1. Read `AGENTS.md`.
2. Query or grep relevant traces and policies before opening code.
3. Load at most the top five relevant memory artifacts.
4. Only then open source files.
5. Promote repeatable task decisions into `policies/`.

Trace priority:

1. `manual_curated`
2. `task_capture`
3. `git_backfill`
"""

POLICIES_README = """# Policies

Store only stable, repeatable repository rules here.

Do not copy one-off task traces into this directory until they become durable
engineering policy.

When a trace reveals a long-lived rule, promote it here with
`python -m scripts.repo_memory.promote_policy ...`.
"""


class TraceValidationError(ValueError):
    pass


@dataclass(slots=True)
class TraceDocument:
    path: Path | None
    metadata: dict[str, Any]
    title: str
    sections: dict[str, str]
    raw_text: str


@dataclass(slots=True)
class RankedTrace:
    document: TraceDocument
    score: float


def context_graph_root(repo_root: Path) -> Path:
    return repo_root / CONTEXT_GRAPH_DIR


def traces_root(repo_root: Path) -> Path:
    return context_graph_root(repo_root) / 'traces'


def policies_root(repo_root: Path) -> Path:
    return context_graph_root(repo_root) / 'policies'


def manifest_path(repo_root: Path) -> Path:
    return context_graph_root(repo_root) / 'backfill_manifest.json'


def shadow_mode_log_path(repo_root: Path) -> Path:
    return context_graph_root(repo_root) / 'shadow_mode_log.jsonl'


def current_timestamp() -> str:
    return datetime.now(UTC).isoformat()


def ensure_context_graph_scaffold(repo_root: Path) -> list[Path]:
    graph_root = context_graph_root(repo_root)
    traces_dir = graph_root / 'traces'
    policies_dir = policies_root(repo_root)
    traces_dir.mkdir(parents=True, exist_ok=True)
    policies_dir.mkdir(parents=True, exist_ok=True)

    created_paths: list[Path] = []
    file_specs = {
        graph_root / 'README.md': CONTEXT_GRAPH_README,
        graph_root / 'trace_schema.md': TRACE_SCHEMA_MARKDOWN,
        graph_root / 'trace_template.md': TRACE_TEMPLATE_MARKDOWN,
        policies_dir / 'README.md': POLICIES_README,
        traces_dir / '.gitkeep': '',
    }
    for path, content in file_specs.items():
        if not path.exists():
            path.write_text(content, encoding='utf-8')
            created_paths.append(path)

    manifest = manifest_path(repo_root)
    if not manifest.exists():
        manifest.write_text(
            json.dumps(
                {
                    'schema_version': TRACE_SCHEMA_VERSION,
                    'backfill': {
                        'processed_commits': [],
                        'last_run_at': None,
                        'last_limit': None,
                        'last_rev_range': None,
                    },
                },
                indent=2,
            )
            + '\n',
            encoding='utf-8',
        )
        created_paths.append(manifest)

    return created_paths


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith('---\n'):
        raise TraceValidationError('Trace frontmatter must start with ---')

    try:
        _, raw_frontmatter, body = text.split('---\n', 2)
    except ValueError as exc:
        raise TraceValidationError(
            'Trace frontmatter must be closed with ---'
        ) from exc

    metadata: dict[str, Any] = {}
    for key, raw_value in _iter_frontmatter_items(raw_frontmatter):
        metadata[key] = _parse_frontmatter_value(raw_value)

    return metadata, body


def _iter_frontmatter_items(
    raw_frontmatter: str,
) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    lines = raw_frontmatter.strip().splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue

        match = re.match(r'^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$', line)
        if match is None:
            raise TraceValidationError(f'Invalid frontmatter line: {line}')

        key = match.group(1)
        value_lines = [match.group(2)] if match.group(2) else []
        index += 1
        while index < len(lines):
            next_line = lines[index]
            if re.match(r'^[A-Za-z_][A-Za-z0-9_-]*:', next_line):
                break
            if next_line.strip():
                value_lines.append(next_line.strip())
            index += 1
        items.append((key, '\n'.join(value_lines).strip()))
    return items


def _parse_frontmatter_value(raw_value: str) -> Any:
    raw_value = raw_value.strip()
    if raw_value.startswith('['):
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError:
            try:
                parsed = ast.literal_eval(raw_value)
            except (SyntaxError, ValueError) as exc:
                raise TraceValidationError(
                    f'Invalid frontmatter list value: {raw_value}'
                ) from exc
        if not isinstance(parsed, list):
            raise TraceValidationError('Frontmatter list value must be a list')
        return parsed
    return raw_value


def format_trace_document(
    *,
    metadata: dict[str, Any],
    title: str,
    sections: dict[str, str],
) -> str:
    lines = ['---']
    for key in REQUIRED_FRONTMATTER_KEYS:
        value = metadata[key]
        if isinstance(value, list):
            rendered = json.dumps(value, ensure_ascii=False)
        else:
            rendered = str(value)
        lines.append(f'{key}: {rendered}')
    lines.append('---')
    lines.append(f'# {title}')
    lines.append('')
    for section_name in REQUIRED_SECTIONS:
        lines.append(f'## {section_name}')
        lines.append(sections[section_name].strip())
        lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


def validate_trace_document(text: str) -> TraceDocument:
    metadata, body = parse_frontmatter(text)
    missing_keys = [
        key for key in REQUIRED_FRONTMATTER_KEYS if key not in metadata
    ]
    if missing_keys:
        raise TraceValidationError(
            f'Missing frontmatter keys: {", ".join(missing_keys)}'
        )

    if metadata['source_type'] not in VALID_SOURCE_TYPES:
        raise TraceValidationError('Invalid source_type')
    if metadata['confidence'] not in VALID_CONFIDENCE:
        raise TraceValidationError('Invalid confidence')
    if metadata['status'] not in VALID_STATUS:
        raise TraceValidationError('Invalid status')

    for list_key in ('paths', 'tags', 'commit_shas', 'supersedes'):
        if not isinstance(metadata[list_key], list):
            raise TraceValidationError(f'{list_key} must be a list')

    title, sections = _parse_trace_body(body)
    for section_name in REQUIRED_SECTIONS:
        value = sections.get(section_name, '').strip()
        if not value:
            raise TraceValidationError(
                f'Missing or empty section: {section_name}'
            )

    return TraceDocument(
        path=None,
        metadata=metadata,
        title=title,
        sections=sections,
        raw_text=text,
    )


def _parse_trace_body(body: str) -> tuple[str, dict[str, str]]:
    stripped_body = body.strip()
    title_match = re.match(r'^# (.+)$', stripped_body, re.MULTILINE)
    if title_match is None:
        raise TraceValidationError('Trace must start with a level-1 title')
    title = title_match.group(1).strip()

    sections: dict[str, str] = {}
    matches = list(re.finditer(r'^## (.+)$', stripped_body, re.MULTILINE))
    for index, match in enumerate(matches):
        section_name = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else None
        sections[section_name] = stripped_body[start:end].strip()
    return title, sections


def load_trace_document(path: Path) -> TraceDocument:
    document = validate_trace_document(path.read_text(encoding='utf-8'))
    document.path = path
    return document


def find_broken_links(trace_path: Path, repo_root: Path) -> list[str]:
    link_targets = re.findall(
        r'\[[^\]]+\]\(([^)]+)\)',
        trace_path.read_text(encoding='utf-8'),
    )
    broken: list[str] = []
    for target in link_targets:
        if target.startswith(('http://', 'https://', 'mailto:')):
            continue
        target_path = (
            repo_root / target.lstrip('/')
            if target.startswith('/')
            else repo_root / target
        )
        if not target_path.exists():
            broken.append(target)
    return broken


def validate_trace_collection(
    trace_paths: list[Path],
    *,
    repo_root: Path,
) -> list[TraceDocument]:
    documents: list[TraceDocument] = []
    seen_ids: dict[str, Path] = {}
    for path in trace_paths:
        document = load_trace_document(path)
        trace_id = str(document.metadata['trace_id'])
        if trace_id in seen_ids:
            raise TraceValidationError(
                f'Duplicate trace_id "{trace_id}" in {path} and '
                f'{seen_ids[trace_id]}'
            )
        seen_ids[trace_id] = path

        broken_links = find_broken_links(path, repo_root=repo_root)
        if broken_links:
            raise TraceValidationError(
                f'Broken links in {path}: {", ".join(broken_links)}'
            )
        documents.append(document)
    return documents


def tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r'[a-z0-9][a-z0-9_-]*', text.lower())
        if len(token) > 1
    }


def rank_trace_documents(
    *,
    documents: list[TraceDocument],
    query: str,
    query_paths: list[str],
    limit: int,
) -> list[RankedTrace]:
    query_tokens = tokenize(query)
    ranked: list[RankedTrace] = []
    for document in documents:
        score = score_trace_document(
            document=document,
            query_tokens=query_tokens,
            query_paths=query_paths,
        )
        ranked.append(RankedTrace(document=document, score=score))

    return sorted(
        ranked,
        key=lambda item: (
            item.score,
            item.document.metadata['created_at'],
            item.document.metadata['trace_id'],
        ),
        reverse=True,
    )[:limit]


def score_trace_document(
    *,
    document: TraceDocument,
    query_tokens: set[str],
    query_paths: list[str],
) -> float:
    metadata = document.metadata
    title_tokens = tokenize(document.title)
    tag_tokens = tokenize(' '.join(str(tag) for tag in metadata['tags']))
    section_tokens = tokenize(' '.join(document.sections.values()))

    score = 0.0
    score += 5.0 * len(query_tokens & title_tokens)
    score += 4.0 * len(query_tokens & tag_tokens)
    score += 1.5 * len(query_tokens & section_tokens)
    score += _score_path_token_overlap(
        query_tokens=query_tokens,
        trace_paths=metadata['paths'],
    )
    score += _score_bigram_overlap(
        query_tokens=query_tokens,
        title_tokens=title_tokens,
    )
    score += _score_path_overlap(query_paths, metadata['paths'])
    score += _score_focus(len(query_paths), len(metadata['paths']))
    score += _score_source_type(str(metadata['source_type']))
    score += _score_confidence(str(metadata['confidence']))
    score += _score_status(str(metadata['status']))
    score += _score_freshness(str(metadata['created_at']))
    return score


def _score_path_overlap(
    query_paths: list[str],
    trace_paths: list[str],
) -> float:
    score = 0.0
    for query_path in query_paths:
        normalized_query = query_path.strip('/')
        if not normalized_query:
            continue
        best = max(
            (
                _score_path_pair(
                    normalized_query=normalized_query,
                    normalized_trace=str(trace_path).strip('/'),
                )
                for trace_path in trace_paths
            ),
            default=0.0,
        )
        score += best
    if query_paths and trace_paths:
        exact_matches = sum(
            1
            for query_path in query_paths
            if any(
                query_path.strip('/') == str(trace_path).strip('/')
                for trace_path in trace_paths
            )
        )
        if exact_matches == len(query_paths):
            score += 6.0
    return score


def _score_path_pair(
    *,
    normalized_query: str,
    normalized_trace: str,
) -> float:
    if not normalized_query or not normalized_trace:
        return 0.0
    if normalized_query == normalized_trace:
        return 24.0

    query_parts = Path(normalized_query).parts
    trace_parts = Path(normalized_trace).parts

    if normalized_trace.startswith(f'{normalized_query}/'):
        return 18.0
    if normalized_query.startswith(f'{normalized_trace}/'):
        return 14.0

    common_prefix = 0
    for query_part, trace_part in zip(query_parts, trace_parts, strict=False):
        if query_part != trace_part:
            break
        common_prefix += 1

    common_parts = len(set(query_parts) & set(trace_parts))
    score = min(common_prefix * 4.0, 16.0)
    score += min(common_parts * 1.5, 6.0)

    query_path = Path(normalized_query)
    trace_path = Path(normalized_trace)
    if query_path.name == trace_path.name:
        score += 8.0
    if query_path.stem == trace_path.stem:
        score += 4.0
    return score


def _score_path_token_overlap(
    *,
    query_tokens: set[str],
    trace_paths: list[str],
) -> float:
    path_tokens = tokenize(' '.join(str(path) for path in trace_paths))
    return 8.0 * len(query_tokens & path_tokens)


def _score_bigram_overlap(
    *,
    query_tokens: set[str],
    title_tokens: set[str],
) -> float:
    return 2.0 * len(query_tokens & title_tokens)


def _score_focus(query_path_count: int, trace_path_count: int) -> float:
    if query_path_count <= 0:
        return 0.0
    expected_size = max(8, query_path_count * 4)
    if trace_path_count <= expected_size:
        return 3.0
    overflow = trace_path_count - expected_size
    return -min(overflow * 0.3, 10.0)


def _score_source_type(source_type: str) -> float:
    if source_type == 'manual_curated':
        return 12.0
    if source_type == 'task_capture':
        return 6.0
    return 0.0


def _score_confidence(confidence: str) -> float:
    if confidence == 'high':
        return 8.0
    if confidence == 'medium':
        return 2.0
    return -8.0


def _score_status(status: str) -> float:
    if status == 'deprecated':
        return -20.0
    if status == 'superseded':
        return -10.0
    return 0.0


def _score_freshness(created_at: str) -> float:
    try:
        created = datetime.fromisoformat(created_at)
    except ValueError:
        return 0.0
    age_days = (datetime.now(UTC) - created.astimezone(UTC)).days
    if age_days <= 30:
        return 5.0
    if age_days <= 180:
        return 2.0
    return 0.0


def parse_csv_argument(raw_value: str | list[str] | None) -> list[str]:
    if raw_value is None:
        return []
    raw_values = raw_value if isinstance(raw_value, list) else [raw_value]
    parsed: list[str] = []
    for value in raw_values:
        separators = ',' if ',' in value else None
        parsed.extend(
            item.strip() for item in value.split(separators) if item.strip()
        )
    return parsed


def discover_changed_paths(repo_root: Path) -> list[str]:
    commands = [
        ['git', 'diff', '--name-only', 'HEAD'],
        ['git', 'diff', '--name-only', '--cached', 'HEAD'],
        ['git', 'ls-files', '--others', '--exclude-standard'],
    ]
    paths: set[str] = set()
    for command in commands:
        result = subprocess.run(
            command,
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            continue
        for line in result.stdout.splitlines():
            normalized = line.strip()
            if normalized:
                paths.add(normalized)
    return sorted(paths)


def current_head_sha(repo_root: Path) -> str | None:
    result = subprocess.run(
        ['git', 'rev-parse', 'HEAD'],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    sha = result.stdout.strip()
    return sha or None


def write_trace_file(
    *,
    repo_root: Path,
    filename: str,
    content: str,
) -> Path:
    path = traces_root(repo_root) / filename
    path.write_text(content, encoding='utf-8')
    return path
