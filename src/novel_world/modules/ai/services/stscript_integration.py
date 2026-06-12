from __future__ import annotations

from typing import Any

from novel_world.modules.stscript.engine import STScriptEngine


def apply_stscript(
    event: str,
    text: str,
    *,
    user_prefs: dict[str, Any] | None,
    session_config: dict[str, Any] | None,
) -> tuple[str, dict[str, Any] | None]:
    engine = STScriptEngine.from_prefs_and_session(user_prefs, session_config)
    out = engine.apply_event(event, text)
    patch = engine.scope_patch()
    return out, patch
