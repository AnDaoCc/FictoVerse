from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class STCommand:
    name: str
    args: list[str] = field(default_factory=list)
    raw: str = ""


@dataclass
class STScript:
    name: str = ""
    content: str = ""
    enabled: bool = True
    triggers: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
