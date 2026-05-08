# build-context-graph

Source repository for the `build-context-graph` Codex skill.

The skill bootstraps or upgrades a repo-local engineering memory layer based on
`.agents/context-graph` and `.agents/context-graph/tools/repo_memory`. After
installation, agents should use the target repository's repo-local toolkit for
daily retrieval, validation, trace capture, and policy promotion.

## Layout

- `SKILL.md` - skill trigger metadata and core workflow.
- `agents/openai.yaml` - skill UI metadata.
- `scripts/bootstrap_repo_memory.py` - installer for target repositories.
- `scripts/templates/repo_memory/` - toolkit copied into target repositories.
- `scripts/evaluate_retrieval_benchmark.py` - optional cutover benchmark
  evaluator.
- `references/` - detailed adoption, benchmark, and policy-promotion guidance.

## Install Globally

Sync the source repo into the global Codex skill directory:

```bash
rsync -a --delete \
  --exclude '.git' \
  --exclude '__pycache__' \
  --exclude 'README.md' \
  ./ /Users/solmax/.codex/skills/build-context-graph/
```

Use a different Codex home by replacing `/Users/solmax/.codex`.

`README.md` is intentionally excluded from the installed skill copy. Keep
runtime instructions in `SKILL.md` and deeper operational guidance in
`references/`.

## Bootstrap A Repository

Run the installer from this source repository:

```bash
python scripts/bootstrap_repo_memory.py --repo-root /path/to/repo
```

Then validate from the target repository:

```bash
cd /path/to/repo
PYTHONPATH=.agents/context-graph/tools python -m repo_memory.validate --repo-root .
PYTHONPATH=.agents/context-graph/tools python -m repo_memory.query \
  --text "repo memory smoke" \
  --paths AGENTS.md \
  --include-policies
```

Add the retrieval workflow printed by the installer to the target repository's
`AGENTS.md`. If a legacy memory workflow exists, keep it as fallback until
shadow-mode evidence supports cutover.

## Validate This Skill

Run a syntax check after changing Python scripts:

```bash
python -m py_compile \
  scripts/bootstrap_repo_memory.py \
  scripts/evaluate_retrieval_benchmark.py \
  scripts/templates/repo_memory/*.py
```

Smoke-install into a temporary repository when changing the installer or
`scripts/templates/repo_memory`:

```bash
tmpdir=$(mktemp -d /tmp/context-graph-skill.XXXXXX)
git -C "$tmpdir" init -q
python scripts/bootstrap_repo_memory.py --repo-root "$tmpdir"
(
  cd "$tmpdir"
  PYTHONPATH=.agents/context-graph/tools python -m repo_memory.validate --repo-root .
)
rm -rf "$tmpdir"
```

## Release Checklist

- Keep `SKILL.md` concise; put detailed guidance in `references/`.
- Do not commit `__pycache__`, local smoke repositories, generated logs, or
  target-repo context data.
- Smoke-test bootstrap after changing `scripts/templates/repo_memory`.
- Sync the global installed copy only after source validation passes.
