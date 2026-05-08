#!/usr/bin/env python3
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            'Install the repo_memory toolkit into a target repository.'
        ),
    )
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument(
        '--toolkit-dir',
        default='.agents/context-graph/tools/repo_memory',
        help='Relative path inside the target repo for the installed toolkit.',
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Overwrite an existing toolkit directory.',
    )
    return parser.parse_args(argv)


def _template_root() -> Path:
    return Path(__file__).resolve().parent / 'templates' / 'repo_memory'


def _copy_tree(source_root: Path, target_root: Path, *, force: bool) -> None:
    if target_root.exists():
        if not force:
            raise FileExistsError(
                f'Toolkit directory already exists: {target_root}. '
                'Use --force to overwrite it.'
            )
        shutil.rmtree(target_root)
    shutil.copytree(source_root, target_root)


def _run_bootstrap(repo_root: Path, toolkit_dir: Path) -> None:
    env = {
        **dict(os.environ),
        'PYTHONPATH': str((repo_root / toolkit_dir.parent).resolve()),
    }
    subprocess.run(
        [
            sys.executable,
            '-m',
            'repo_memory.bootstrap',
            '--repo-root',
            str(repo_root),
        ],
        cwd=repo_root,
        env=env,
        check=True,
    )


def _agents_snippet() -> str:
    return (
        '1. Read AGENTS.md.\n'
        '2. For substantial tasks, start retrieval with '
        '`PYTHONPATH=.agents/context-graph/tools python -m '
        'repo_memory.query --text ... --paths ... --include-policies`.\n'
        '3. Load at most five relevant traces or policies before reading '
        'source files.\n'
        '4. If retrieval looks weak or the task changes memory workflow '
        'behavior, run `PYTHONPATH=.agents/context-graph/tools python -m '
        'repo_memory.shadow_mode --task-summary ... --query ... '
        '--paths ...`.\n'
        '5. After material changes, capture a trace with '
        '`PYTHONPATH=.agents/context-graph/tools python -m '
        'repo_memory.capture ...`.\n'
        '6. Promote stable rules with '
        '`PYTHONPATH=.agents/context-graph/tools python -m '
        'repo_memory.promote_policy ...`.'
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    repo_root = args.repo_root.resolve()
    if not repo_root.exists():
        raise FileNotFoundError(f'Repository root not found: {repo_root}')

    target_root = repo_root / args.toolkit_dir
    target_root.parent.mkdir(parents=True, exist_ok=True)
    _copy_tree(_template_root(), target_root, force=args.force)
    _run_bootstrap(repo_root, Path(args.toolkit_dir))

    print(f'Installed repo_memory toolkit at {target_root}')
    print('\nSuggested AGENTS.md snippet:\n')
    print(_agents_snippet())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
