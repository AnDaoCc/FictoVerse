from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

LoreScope = Literal["world", "character", "session"]
LorePosition = Literal["before_main", "after_char", "before_examples", "at_depth", "post_history"]
LoreSource = Literal["manual", "character_book", "document", "st_import", "session"]
LoreFilterType = Literal["include", "exclude"]

LoreEntryId = str


def new_lore_entry_id() -> LoreEntryId:
    return str(uuid.uuid4())


@dataclass
class LoreEntry:
    id: LoreEntryId
    scope: LoreScope = "world"
    character_id: str = ""
    keys: list[str] = field(default_factory=list)
    keys_secondary: list[str] = field(default_factory=list)
    selective_logic: int = 0
    match_whole_words: bool = False
    use_vector: bool = False
    vectorized: bool = False
    content: str = ""
    constant: bool = False
    selective: bool = True
    recursive: bool = False
    priority: int = 0
    insertion_order: int = 0
    position: LorePosition = "before_main"
    depth: int = 4
    enabled: bool = True
    comment: str = ""
    source: LoreSource = "manual"
    source_ref: str = ""
    probability: float = 1.0
    lore_group: str = ""
    group_override: bool = False
    group_weight: int = 100
    cooldown: int = 0
    sticky: int = 0
    character_filter: list[str] = field(default_factory=list)
    filter_type: LoreFilterType = "include"
    scan_depth: int = 0
    use_group_scoring: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "scope": self.scope,
            "character_id": self.character_id,
            "keys": list(self.keys),
            "keys_secondary": list(self.keys_secondary),
            "selective_logic": self.selective_logic,
            "match_whole_words": self.match_whole_words,
            "use_vector": self.use_vector,
            "vectorized": self.vectorized,
            "content": self.content,
            "constant": self.constant,
            "selective": self.selective,
            "recursive": self.recursive,
            "priority": self.priority,
            "insertion_order": self.insertion_order,
            "position": self.position,
            "depth": self.depth,
            "enabled": self.enabled,
            "comment": self.comment,
            "source": self.source,
            "source_ref": self.source_ref,
            "probability": self.probability,
            "lore_group": self.lore_group,
            "group_override": self.group_override,
            "group_weight": self.group_weight,
            "cooldown": self.cooldown,
            "sticky": self.sticky,
            "character_filter": list(self.character_filter),
            "filter_type": self.filter_type,
            "scan_depth": self.scan_depth,
            "use_group_scoring": self.use_group_scoring,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LoreEntry:
        keys = data.get("keys") or []
        keys_sec = data.get("keys_secondary") or []
        filt = data.get("character_filter") or []
        return cls(
            id=str(data.get("id") or new_lore_entry_id()),
            scope=data.get("scope", "world"),  # type: ignore[arg-type]
            character_id=str(data.get("character_id", "")),
            keys=[str(k) for k in keys] if isinstance(keys, list) else [],
            keys_secondary=[str(k) for k in keys_sec] if isinstance(keys_sec, list) else [],
            selective_logic=int(data.get("selective_logic") or 0),
            match_whole_words=bool(data.get("match_whole_words", False)),
            use_vector=bool(data.get("use_vector", False)),
            vectorized=bool(data.get("vectorized", False)),
            content=str(data.get("content", "")),
            constant=bool(data.get("constant", False)),
            selective=bool(data.get("selective", True)),
            recursive=bool(data.get("recursive", False)),
            priority=int(data.get("priority") or 0),
            insertion_order=int(data.get("insertion_order") or 0),
            position=data.get("position", "before_main"),  # type: ignore[arg-type]
            depth=int(data.get("depth") or 4),
            enabled=bool(data.get("enabled", True)),
            comment=str(data.get("comment", "")),
            source=data.get("source", "manual"),  # type: ignore[arg-type]
            source_ref=str(data.get("source_ref", "")),
            probability=float(data.get("probability", 1.0) or 1.0),
            lore_group=str(data.get("lore_group") or data.get("group") or ""),
            group_override=bool(data.get("group_override", False)),
            group_weight=int(data.get("group_weight") or 100),
            cooldown=int(data.get("cooldown") or 0),
            sticky=int(data.get("sticky") or 0),
            character_filter=[str(x) for x in filt] if isinstance(filt, list) else [],
            filter_type=data.get("filter_type", "include"),  # type: ignore[arg-type]
            scan_depth=int(data.get("scan_depth") or 0),
            use_group_scoring=bool(data.get("use_group_scoring", False)),
        )
