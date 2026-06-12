from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

PromptTemplate = Literal["chat", "chatml", "alpaca"]


@dataclass
class AuthorsNote:
    content: str = ""
    depth: int = 4


@dataclass
class PromptLayers:
    main: str = ""
    jailbreak: str = ""
    system_extra: str = ""
    authors_note: AuthorsNote = field(default_factory=AuthorsNote)
    post_history: str = ""
    template: PromptTemplate = "chat"

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> PromptLayers:
        if not isinstance(data, dict):
            return cls()
        an_raw = data.get("authors_note") or {}
        if isinstance(an_raw, str):
            an = AuthorsNote(content=an_raw)
        elif isinstance(an_raw, dict):
            an = AuthorsNote(
                content=str(an_raw.get("content", "")),
                depth=int(an_raw.get("depth", 4)),
            )
        else:
            an = AuthorsNote()
        template = str(data.get("template", "chat"))
        if template not in ("chat", "chatml", "alpaca"):
            template = "chat"
        return cls(
            main=str(data.get("main", "")),
            jailbreak=str(data.get("jailbreak", "")),
            system_extra=str(data.get("system_extra", "")),
            authors_note=an,
            post_history=str(data.get("post_history", "")),
            template=template,  # type: ignore[arg-type]
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "main": self.main,
            "jailbreak": self.jailbreak,
            "system_extra": self.system_extra,
            "authors_note": {"content": self.authors_note.content, "depth": self.authors_note.depth},
            "post_history": self.post_history,
            "template": self.template,
        }
