from __future__ import annotations



from dataclasses import dataclass, field

from typing import Any



CARD_SPEC = "chara_card_v2"

CARD_SPEC_VERSION = "2.0"

CARD_SPEC_V3 = "chara_card_v3"

CARD_SPEC_VERSION_V3 = "3.0"





@dataclass

class CharacterCard:

    """SillyTavern V2/V3 角色卡（子集 + extensions round-trip）。"""



    name: str = ""

    description: str = ""

    personality: str = ""

    scenario: str = ""

    first_mes: str = ""

    mes_example: str = ""

    system_prompt: str = ""

    post_history_instructions: str = ""

    alternate_greetings: list[str] = field(default_factory=list)

    group_only_greetings: list[str] = field(default_factory=list)

    tags: list[str] = field(default_factory=list)

    creator: str = ""

    character_version: str = ""

    creator_notes: str = ""

    extensions: dict[str, Any] = field(default_factory=dict)

    character_book: dict[str, Any] | list[Any] | None = None

    card_spec: str = CARD_SPEC

    card_spec_version: str = CARD_SPEC_VERSION



    def _data_dict(self) -> dict[str, Any]:

        data: dict[str, Any] = {

            "name": self.name,

            "description": self.description,

            "personality": self.personality,

            "scenario": self.scenario,

            "first_mes": self.first_mes,

            "mes_example": self.mes_example,

            "creator_notes": self.creator_notes,

            "system_prompt": self.system_prompt,

            "post_history_instructions": self.post_history_instructions,

            "alternate_greetings": list(self.alternate_greetings),

            "tags": list(self.tags),

            "creator": self.creator,

            "character_version": self.character_version,

            "extensions": dict(self.extensions),

        }

        if self.group_only_greetings:

            data["group_only_greetings"] = list(self.group_only_greetings)

        if self.character_book is not None:

            data["character_book"] = self.character_book

        return data



    def to_v2_dict(self) -> dict[str, Any]:

        return {

            "spec": CARD_SPEC,

            "spec_version": CARD_SPEC_VERSION,

            "data": self._data_dict(),

        }



    def to_v3_dict(self) -> dict[str, Any]:

        return {

            "spec": CARD_SPEC_V3,

            "spec_version": CARD_SPEC_VERSION_V3,

            "data": self._data_dict(),

        }



    def to_export_dict(self, *, prefer_v3: bool = True) -> dict[str, Any]:

        if prefer_v3 or self.card_spec == CARD_SPEC_V3:

            return self.to_v3_dict()

        return self.to_v2_dict()



    @classmethod

    def from_v2_dict(cls, raw: dict[str, Any]) -> CharacterCard:

        spec = str(raw.get("spec", "")).strip() or CARD_SPEC

        spec_version = str(raw.get("spec_version", "")).strip() or (

            CARD_SPEC_VERSION_V3 if spec == CARD_SPEC_V3 else CARD_SPEC_VERSION

        )

        data = raw.get("data") if isinstance(raw.get("data"), dict) else raw

        if not isinstance(data, dict):

            data = {}



        alt = data.get("alternate_greetings") or []

        group_alt = data.get("group_only_greetings") or []

        tags = data.get("tags") or []

        extensions = data.get("extensions") or {}

        book = data.get("character_book")



        return cls(

            name=str(data.get("name", "")).strip(),

            description=str(data.get("description", "")).strip(),

            personality=str(data.get("personality", "")).strip(),

            scenario=str(data.get("scenario", "")).strip(),

            first_mes=str(data.get("first_mes", "")).strip(),

            mes_example=str(data.get("mes_example", "")).strip(),

            system_prompt=str(data.get("system_prompt", "")).strip(),

            post_history_instructions=str(data.get("post_history_instructions", "")).strip(),

            alternate_greetings=[str(x) for x in alt] if isinstance(alt, list) else [],

            group_only_greetings=[str(x) for x in group_alt] if isinstance(group_alt, list) else [],

            tags=[str(x) for x in tags] if isinstance(tags, list) else [],

            creator=str(data.get("creator", "")).strip(),

            character_version=str(data.get("character_version", "")).strip(),

            creator_notes=str(data.get("creator_notes", "")).strip(),

            extensions=dict(extensions) if isinstance(extensions, dict) else {},

            character_book=book if book is not None else None,

            card_spec=spec if spec in (CARD_SPEC, CARD_SPEC_V3) else CARD_SPEC,

            card_spec_version=spec_version,

        )


