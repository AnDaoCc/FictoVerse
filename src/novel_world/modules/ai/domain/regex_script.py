from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# SillyTavern regex_placement 数值
PLACEMENT_USER_INPUT = 1
PLACEMENT_AI_OUTPUT = 2
PLACEMENT_SLASH_COMMAND = 3
PLACEMENT_WORLD_INFO = 4
PLACEMENT_AUTHOR_NOTE = 5
PLACEMENT_USER_DISPLAY = 6
PLACEMENT_USER_DISPLAY_ONLY = 7


@dataclass
class RegexScript:
    id: str = ""
    script_name: str = ""
    find_regex: str = ""
    replace_string: str = ""
    trim_strings: list[str] = field(default_factory=list)
    placement: list[int] = field(default_factory=list)
    disabled: bool = False
    markdown_only: bool = False
    prompt_only: bool = False
    run_on_edit: bool = False
    substitute_regex: int = 0
    min_depth: int | None = None
    max_depth: int | None = None
    macro_mode: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "scriptName": self.script_name,
            "findRegex": self.find_regex,
            "replaceString": self.replace_string,
            "trimStrings": list(self.trim_strings),
            "placement": list(self.placement),
            "disabled": self.disabled,
            "markdownOnly": self.markdown_only,
            "promptOnly": self.prompt_only,
            "runOnEdit": self.run_on_edit,
            "substituteRegex": self.substitute_regex,
            "minDepth": self.min_depth,
            "maxDepth": self.max_depth,
            "macroMode": self.macro_mode,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, script_id: str = "") -> RegexScript:
        placement = data.get("placement") or []
        if isinstance(placement, int):
            placement = [placement]
        trim = data.get("trimStrings") or []
        min_d = data.get("minDepth")
        max_d = data.get("maxDepth")
        return cls(
            id=script_id or str(data.get("id") or data.get("scriptName") or ""),
            script_name=str(data.get("scriptName") or data.get("name") or ""),
            find_regex=str(data.get("findRegex") or data.get("pattern") or ""),
            replace_string=str(data.get("replaceString") or data.get("replace") or ""),
            trim_strings=[str(x) for x in trim] if isinstance(trim, list) else [],
            placement=[int(x) for x in placement] if isinstance(placement, list) else [],
            disabled=bool(data.get("disabled", False)),
            markdown_only=bool(data.get("markdownOnly", False)),
            prompt_only=bool(data.get("promptOnly", False)),
            run_on_edit=bool(data.get("runOnEdit", False)),
            substitute_regex=int(data.get("substituteRegex") or 0),
            min_depth=int(min_d) if min_d is not None else None,
            max_depth=int(max_d) if max_d is not None else None,
            macro_mode=str(data.get("macroMode") or ""),
        )
