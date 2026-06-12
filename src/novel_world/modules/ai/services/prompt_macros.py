from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

_MACRO_PATTERN = re.compile(
    r"\{\{\s*"
    r"(char|user|persona|description|char_desc|personality|scenario|world|lore|time|date|"
    r"newline|trim|random|idle_duration|max_context|bias|roll(?::\s*d?\d+)?)"
    r"\s*\}\}",
    re.IGNORECASE,
)


@dataclass
class MacroContext:
    char_name: str = ""
    user_name: str = ""
    persona_text: str = ""
    description: str = ""
    personality: str = ""
    scenario: str = ""
    world_name: str = ""
    lore_text: str = ""
    max_context: str = ""
    bias: str = ""
    idle_duration: str = ""
    _rng: random.Random = field(default_factory=random.Random)

    def mapping(self) -> dict[str, str]:
        desc = self.description or ""
        now = datetime.now()
        return {
            "char": self.char_name,
            "user": self.user_name,
            "persona": self.persona_text,
            "description": desc,
            "char_desc": desc,
            "personality": self.personality,
            "scenario": self.scenario,
            "world": self.world_name,
            "lore": self.lore_text,
            "time": now.strftime("%H:%M"),
            "date": now.strftime("%Y-%m-%d"),
            "newline": "\n",
            "trim": "",
            "random": f"{self._rng.random():.4f}",
            "idle_duration": self.idle_duration,
            "max_context": self.max_context,
            "bias": self.bias,
        }


def apply_macros(text: str, ctx: MacroContext | None) -> str:
    if not text or ctx is None:
        return text or ""

    mapping = ctx.mapping()

    def _repl(match: re.Match[str]) -> str:
        raw = match.group(1).lower()
        if raw.startswith("roll"):
            m = re.match(r"roll(?::\s*d?(\d+))?", raw)
            sides = int(m.group(1)) if m and m.group(1) else 6
            return str(ctx._rng.randint(1, max(1, sides)))
        key = raw
        return mapping.get(key, match.group(0))

    return _MACRO_PATTERN.sub(_repl, text)


def apply_macros_to_layers(layers: Any, ctx: MacroContext | None) -> Any:
    if ctx is None or layers is None:
        return layers
    layers.main = apply_macros(layers.main, ctx)
    layers.jailbreak = apply_macros(layers.jailbreak, ctx)
    layers.system_extra = apply_macros(layers.system_extra, ctx)
    layers.post_history = apply_macros(layers.post_history, ctx)
    if layers.authors_note.content:
        layers.authors_note.content = apply_macros(layers.authors_note.content, ctx)
    return layers


def build_macro_context(
    *,
    char_name: str = "",
    user_name: str = "",
    persona: dict[str, Any] | None = None,
    character_profile: dict[str, Any] | None = None,
    world_name: str = "",
    lore_text: str = "",
    max_context: str = "",
    bias: str = "",
    idle_duration: str = "",
) -> MacroContext:
    persona = persona or {}
    profile = character_profile or {}
    persona_text = str(persona.get("description") or persona.get("summary") or "").strip()
    if not persona_text:
        persona_text = str(persona.get("name") or "").strip()
    return MacroContext(
        char_name=char_name.strip(),
        user_name=user_name.strip(),
        persona_text=persona_text,
        description=str(profile.get("description") or profile.get("summary") or "").strip(),
        personality=str(profile.get("personality") or "").strip(),
        scenario=str(profile.get("scenario") or "").strip(),
        world_name=world_name.strip(),
        lore_text=lore_text.strip(),
        max_context=str(max_context or ""),
        bias=str(bias or ""),
        idle_duration=str(idle_duration or ""),
    )
