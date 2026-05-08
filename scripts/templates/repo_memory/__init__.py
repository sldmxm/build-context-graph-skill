__all__ = [
    'audit',
    'backfill_git',
    'bootstrap',
    'capture',
    'promote_policy',
    'query',
    'shadow_mode',
    'validate',
]


def __getattr__(name: str):
    if name not in __all__:
        raise AttributeError(name)

    import importlib

    return importlib.import_module(f'repo_memory.{name}')
