from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from novel_world.modules.ai.domain.generation_config import GenerationConfig
from novel_world.modules.ai.domain.prompt_layers import PromptLayers, PromptTemplate


@dataclass
class PromptSlot:
    identifier: str
    content: str = ""
    enabled: bool = True
    depth: int | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "identifier": self.identifier,
            "content": self.content,
            "enabled": self.enabled,
        }
        if self.depth is not None:
            out["depth"] = self.depth
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PromptSlot:
        depth = data.get("depth")
        return cls(
            identifier=str(data.get("identifier") or data.get("name") or "").strip().lower(),
            content=str(data.get("content") or data.get("system_prompt") or ""),
            enabled=bool(data.get("enabled", True)),
            depth=int(depth) if depth is not None else None,
        )


@dataclass
class PromptProfile:
    slots: list[PromptSlot] = field(default_factory=list)
    order: list[str] = field(default_factory=list)
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    template: PromptTemplate = "chat"

    def slot_map(self) -> dict[str, PromptSlot]:
        return {s.identifier: s for s in self.slots if s.identifier}

    def get_slot(self, identifier: str) -> PromptSlot | None:
        key = identifier.strip().lower()
        return self.slot_map().get(key)

    def slot_content(self, identifier: str) -> str:
        slot = self.get_slot(identifier)
        if slot and slot.enabled:
            return slot.content.strip()
        return ""

    def ordered_slots(self) -> list[PromptSlot]:
        sm = self.slot_map()
        if self.order:
            out: list[PromptSlot] = []
            seen: set[str] = set()
            for ident in self.order:
                key = ident.strip().lower()
                if key in sm and key not in seen:
                    out.append(sm[key])
                    seen.add(key)
            for slot in self.slots:
                if slot.identifier not in seen and slot.enabled:
                    out.append(slot)
            return out
        return [s for s in self.slots if s.enabled]

    def to_layers(self) -> PromptLayers:
        layers = PromptLayers(template=self.template)
        for slot in self.ordered_slots():
            ident = slot.identifier
            if ident == "main":
                layers.main = slot.content
            elif ident in ("jailbreak", "nsfw"):
                layers.jailbreak = (layers.jailbreak + "\n\n" + slot.content).strip()
            elif ident in ("post_history", "postfix"):
                layers.post_history = slot.content
            elif ident in ("authors_note", "an"):
                layers.authors_note.content = slot.content
                if slot.depth is not None:
                    layers.authors_note.depth = slot.depth
            elif ident in ("system_extra", "persona", "scenario"):
                layers.system_extra = (layers.system_extra + "\n\n" + slot.content).strip()
        return layers

    def to_dict(self) -> dict[str, Any]:
        return {
            "slots": [s.to_dict() for s in self.slots],
            "order": list(self.order),
            "generation": self.generation.to_dict(),
            "template": self.template,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> PromptProfile:
        if not isinstance(data, dict):
            return cls()
        slots_raw = data.get("slots") or []
        slots: list[PromptSlot] = []
        if isinstance(slots_raw, list):
            for item in slots_raw:
                if isinstance(item, dict):
                    slots.append(PromptSlot.from_dict(item))
        order_raw = data.get("order") or []
        order = [str(x).strip().lower() for x in order_raw] if isinstance(order_raw, list) else []
        template = str(data.get("template", "chat"))
        if template not in ("chat", "chatml", "alpaca"):
            template = "chat"
        return cls(
            slots=slots,
            order=order,
            generation=GenerationConfig.from_dict(data.get("generation")),
            template=template,  # type: ignore[arg-type]
        )

    @classmethod
    def from_layers(cls, layers: PromptLayers, generation: GenerationConfig | None = None) -> PromptProfile:
        gen = generation or GenerationConfig()
        slots = [
            PromptSlot("main", layers.main),
            PromptSlot("jailbreak", layers.jailbreak),
            PromptSlot("system_extra", layers.system_extra),
            PromptSlot("post_history", layers.post_history),
            PromptSlot(
                "authors_note",
                layers.authors_note.content,
                depth=layers.authors_note.depth,
            ),
        ]
        order = ["main", "system_extra", "jailbreak", "authors_note", "post_history"]
        return cls(slots=slots, order=order, generation=gen, template=layers.template)
