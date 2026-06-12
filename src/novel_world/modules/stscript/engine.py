from __future__ import annotations

import json
from typing import Any

from novel_world.modules.stscript.ast import STScript
from novel_world.modules.stscript.runtime import STScriptRuntime, STScope


def parse_st_scripts_json(data: bytes | str | list | dict) -> list[STScript]:
    if isinstance(data, bytes):
        payload = json.loads(data.decode("utf-8"))
    elif isinstance(data, str):
        payload = json.loads(data)
    else:
        payload = data
    scripts: list[STScript] = []
    items: list[Any]
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("scripts") or payload.get("script") or []
        if isinstance(items, dict):
            items = list(items.values())
    else:
        return scripts
    for item in items:
        if not isinstance(item, dict):
            continue
        triggers = item.get("triggers") or item.get("trigger") or []
        if isinstance(triggers, str):
            triggers = [triggers]
        scripts.append(
            STScript(
                name=str(item.get("name") or item.get("id") or ""),
                content=str(item.get("content") or item.get("script") or ""),
                enabled=not bool(item.get("disabled", False)),
                triggers=[str(t) for t in triggers] if isinstance(triggers, list) else [],
                metadata=dict(item),
            )
        )
    return scripts


class STScriptEngine:
    EVENTS = ("send", "receive", "generate", "idle", "edit", "prompt")

    def __init__(self, scripts: list[STScript] | None = None, scope: STScope | None = None) -> None:
        self._scripts = [s for s in (scripts or []) if s.enabled and s.content.strip()]
        self._scope = scope or STScope()

    @classmethod
    def from_prefs_and_session(
        cls,
        user_prefs: dict[str, Any] | None,
        session_config: dict[str, Any] | None,
    ) -> STScriptEngine:
        scripts: list[STScript] = []
        for item in (user_prefs or {}).get("global_stscripts") or []:
            if isinstance(item, dict):
                scripts.extend(parse_st_scripts_json([item]))
        override = (session_config or {}).get("stscripts_override") or []
        if isinstance(override, list):
            scripts.extend(parse_st_scripts_json(override))
        scope_raw = (session_config or {}).get("stscript_scope") or {}
        scope = STScope(
            global_vars=dict((user_prefs or {}).get("stscript_global_vars") or {}),
            chat_vars=dict(scope_raw.get("chat") or {}),
            local_vars=dict(scope_raw.get("local") or {}),
        )
        return cls(scripts, scope)

    def apply_event(self, event: str, text: str) -> str:
        if event not in self.EVENTS:
            return text
        runtime = STScriptRuntime()
        runtime.scope = self._scope
        out = text
        for script in self._scripts:
            triggers = {t.lower() for t in script.triggers}
            if triggers and event.lower() not in triggers:
                continue
            if "|" in script.content or script.content.strip().startswith("/"):
                out = runtime.run_pipe(script.content, input_text=out)
            else:
                out = runtime.run_command_line(script.content, input_text=out)
        return out

    def scope_patch(self) -> dict[str, Any]:
        return {
            "stscript_scope": {
                "global": dict(self._scope.global_vars),
                "chat": dict(self._scope.chat_vars),
                "local": dict(self._scope.local_vars),
            }
        }
