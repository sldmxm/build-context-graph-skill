import argparse
from pathlib import Path

from repo_memory.shared import ensure_context_graph_scaffold


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Create the repo-sidecar context graph scaffold.',
    )
    parser.add_argument('--repo-root', type=Path, default=Path.cwd())
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    created_paths = ensure_context_graph_scaffold(args.repo_root)
    print(
        f'bootstrap complete: created={len(created_paths)} '
        f'repo_root={args.repo_root}'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
