from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

HookFn = Callable[..., Any]

_REGISTRY: dict[str, list[tuple[int, HookFn]]] = defaultdict(list)


def register_hook(name: str, fn: HookFn, *, priority: int = 100) -> None:
    _REGISTRY[name].append((priority, fn))
    _REGISTRY[name].sort(key=lambda item: item[0])


def clear_hooks(name: str | None = None) -> None:
    if name is None:
        _REGISTRY.clear()
    else:
        _REGISTRY.pop(name, None)


def run_hooks(name: str, value: Any, **context: Any) -> Any:
    result = value
    for _, fn in _REGISTRY.get(name, []):
        try:
            out = fn(result, **context)
            if out is not None:
                result = out
        except Exception:
            continue
    return result


def list_hooks() -> dict[str, int]:
    return {name: len(items) for name, items in _REGISTRY.items()}
