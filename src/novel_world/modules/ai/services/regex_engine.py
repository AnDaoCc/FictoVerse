"""全局 / 会话 Regex 执行引擎（对齐酒馆 placement）。"""
from __future__ import annotations

import re
from typing import Any

from novel_world.modules.ai.domain.regex_script import (
    PLACEMENT_AI_OUTPUT,
    PLACEMENT_AUTHOR_NOTE,
    PLACEMENT_SLASH_COMMAND,
    PLACEMENT_USER_DISPLAY,
    PLACEMENT_USER_DISPLAY_ONLY,
    PLACEMENT_USER_INPUT,
    PLACEMENT_WORLD_INFO,
    RegexScript,
)
from novel_world.modules.ai.services.prompt_macros import MacroContext, apply_macros


def _depth_ok(script: RegexScript, depth: int | None) -> bool:
    if depth is None:
        return True
    if script.min_depth is not None and depth < script.min_depth:
        return False
    if script.max_depth is not None and depth > script.max_depth:
        return False
    return True


def _apply_one(text: str, script: RegexScript, *, macro_ctx: MacroContext | None) -> str:
    if not text or not script.find_regex:
        return text
    pattern = script.find_regex
    repl = apply_macros(script.replace_string, macro_ctx) if script.macro_mode else script.replace_string
    flags = re.DOTALL
    if script.substitute_regex:
        try:
            return re.sub(pattern, repl, text, flags=flags)
        except re.error:
            return text
    try:
        return re.sub(pattern, repl, text, count=0, flags=flags)
    except re.error:
        return text


class RegexEngine:
    def __init__(self, scripts: list[RegexScript] | None = None) -> None:
        self._scripts = [s for s in (scripts or []) if not s.disabled and s.find_regex]

    @classmethod
    def from_prefs_and_session(
        cls,
        user_prefs: dict[str, Any] | None,
        session_config: dict[str, Any] | None,
    ) -> RegexEngine:
        scripts: list[RegexScript] = []
        for item in (user_prefs or {}).get("global_regex_scripts") or []:
            if isinstance(item, dict):
                scripts.append(RegexScript.from_dict(item, script_id=str(item.get("id", ""))))
        override = (session_config or {}).get("regex_scripts_override") or []
        if isinstance(override, list):
            for item in override:
                if isinstance(item, dict):
                    scripts.append(RegexScript.from_dict(item, script_id=str(item.get("id", ""))))
        legacy = (session_config or {}).get("display_scripts") or []
        if isinstance(legacy, list):
            for item in legacy:
                if isinstance(item, dict) and item.get("pattern"):
                    scripts.append(
                        RegexScript(
                            id=str(item.get("id") or ""),
                            script_name="legacy_display",
                            find_regex=str(item.get("pattern")),
                            replace_string=str(item.get("replace", "")),
                            placement=[PLACEMENT_USER_DISPLAY],
                        )
                    )
        return cls(scripts)

    def _for_placement(self, placement: int) -> list[RegexScript]:
        return [s for s in self._scripts if placement in s.placement]

    def apply_slash_command(self, text: str, *, macro_ctx: MacroContext | None = None) -> str:
        out = text
        for script in self._for_placement(PLACEMENT_SLASH_COMMAND):
            out = _apply_one(out, script, macro_ctx=macro_ctx)
        return out

    def apply_user_input(self, text: str, *, macro_ctx: MacroContext | None = None, depth: int | None = None) -> str:
        out = text
        for script in self._for_placement(PLACEMENT_USER_INPUT):
            if _depth_ok(script, depth):
                out = _apply_one(out, script, macro_ctx=macro_ctx)
        return out

    def apply_prompt(self, text: str, *, macro_ctx: MacroContext | None = None) -> str:
        out = text
        for placement in (PLACEMENT_WORLD_INFO, PLACEMENT_AUTHOR_NOTE):
            for script in self._for_placement(placement):
                if script.prompt_only or placement == PLACEMENT_WORLD_INFO:
                    out = _apply_one(out, script, macro_ctx=macro_ctx)
        return out

    def apply_ai_output(
        self,
        text: str,
        *,
        macro_ctx: MacroContext | None = None,
        depth: int | None = None,
        markdown: bool = True,
    ) -> str:
        out = text
        for script in self._for_placement(PLACEMENT_AI_OUTPUT):
            if script.markdown_only and not markdown:
                continue
            if _depth_ok(script, depth):
                out = _apply_one(out, script, macro_ctx=macro_ctx)
        return out

    def apply_display(self, text: str, *, depth: int | None = None) -> str:
        out = text
        for placement in (PLACEMENT_USER_DISPLAY, PLACEMENT_USER_DISPLAY_ONLY):
            for script in self._for_placement(placement):
                if _depth_ok(script, depth):
                    out = _apply_one(out, script, macro_ctx=None)
        return out

    def apply_on_edit(self, text: str, *, macro_ctx: MacroContext | None = None) -> str:
        out = text
        for script in self._scripts:
            if script.run_on_edit:
                out = _apply_one(out, script, macro_ctx=macro_ctx)
        return out
