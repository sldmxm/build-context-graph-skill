import argparse
from pathlib import Path

from scripts.repo_memory.shared import (
    TraceValidationError,
    validate_trace_collection,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Validate context-graph traces.',
    )
    parser.add_argument('--repo-root', type=Path, default=Path.cwd())
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    trace_paths = sorted(
        (args.repo_root / '.agents' / 'context-graph' / 'traces').glob('*.md')
    )
    try:
        documents = validate_trace_collection(
            trace_paths,
            repo_root=args.repo_root,
        )
    except TraceValidationError as exc:
        print(f'validation failed: {exc}')
        return 1

    print(f'validation ok: {len(documents)} trace(s)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
