from __future__ import annotations

import re
from typing import Callable

CommandHandler = Callable[[str, dict], tuple[bool, str]]

_HANDLERS: dict[str, CommandHandler] = {}


def register_command(name: str, handler: CommandHandler) -> None:
    _HANDLERS[name.lower()] = handler


def apply_slash_regex(text: str, ctx: dict | None = None) -> str:
    """对斜杠命令文本应用 Regex placement=3。"""
    prefs = (ctx or {}).get("user_prefs")
    session_config = (ctx or {}).get("session_config")
    if not prefs and not session_config:
        return text
    from novel_world.modules.ai.services.regex_engine import RegexEngine

    regex = RegexEngine.from_prefs_and_session(prefs, session_config)
    return regex.apply_slash_command(text)


def parse_command(text: str, ctx: dict | None = None) -> tuple[bool, str]:
    ctx = ctx or {}
    stripped = (text or "").strip()
    if not stripped.startswith("/"):
        return False, text
    stripped = apply_slash_regex(stripped, ctx)
    parts = stripped.split(maxsplit=1)
    cmd = parts[0][1:].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""
    handler = _HANDLERS.get(cmd)
    if handler is None:
        return False, text
    handled, remainder = handler(arg, ctx)
    if handled:
        return True, remainder
    return False, remainder if remainder else text


def _member_field(member: object, attr: str) -> str:
    return str(getattr(member, attr, "") or "").strip()


def parse_at_mention(
    text: str, members: list, *, name_attr: str = "character_name", id_attr: str = "character_id"
) -> tuple[str, str | None]:
    raw = (text or "").strip()
    if not raw:
        return raw, None

    match = re.match(r"^@(\S+)(?:\s+(.*))?$", raw, re.DOTALL)
    if match:
        token, rest = match.group(1), (match.group(2) or "").strip()
        for member in members:
            name = _member_field(member, name_attr)
            mid = _member_field(member, id_attr)
            if token == name or token == mid:
                return rest, mid
        return raw, None

    ordered = sorted(
        members,
        key=lambda m: len(_member_field(m, name_attr)),
        reverse=True,
    )
    for member in ordered:
        name = _member_field(member, name_attr)
        mid = _member_field(member, id_attr)
        if not name:
            continue
        needle = f"@{name}"
        idx = raw.find(needle)
        if idx < 0:
            continue
        end = idx + len(needle)
        if end < len(raw) and not (raw[end].isspace() or raw[end] in "，。！？,.!?;；"):
            continue
        rest = (raw[:idx] + raw[end:]).strip()
        rest = re.sub(r"\s+", " ", rest).strip()
        return rest, mid

    return raw, None


def register_default_commands() -> None:
    def remember_handler(arg: str, ctx: dict) -> tuple[bool, str]:
        mem = ctx.get("memory")
        sid = ctx.get("session_id")
        if mem and sid and arg.strip():
            mem.pin(sid, arg.strip())
        return True, ""

    register_command("remember", remember_handler)

    def sys_handler(arg: str, ctx: dict) -> tuple[bool, str]:
        mem = ctx.get("memory")
        sid = ctx.get("session_id")
        if mem and sid and arg.strip():
            mem.pin(sid, f"[系统] {arg.strip()}")
        return True, ""

    def ooc_handler(arg: str, _ctx: dict) -> tuple[bool, str]:
        if not arg.strip():
            return True, ""
        return False, f"(({arg.strip()}))"

    register_command("sys", sys_handler)
    register_command("ooc", ooc_handler)
