"""Lore cooldown/sticky 会话状态（存 session.config.lore_state）。"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from novel_world.modules.world.domain.lore_entry import LoreEntry


@dataclass
class LoreSessionState:
    cooldown: dict[str, int] = field(default_factory=dict)
    sticky: dict[str, int] = field(default_factory=dict)
    message_count: int = 0

    @classmethod
    def from_config(cls, config: dict[str, Any] | None) -> LoreSessionState:
        raw = (config or {}).get("lore_state") or {}
        if not isinstance(raw, dict):
            return cls()
        cd = raw.get("cooldown") or {}
        st = raw.get("sticky") or {}
        return cls(
            cooldown={str(k): int(v) for k, v in cd.items()} if isinstance(cd, dict) else {},
            sticky={str(k): int(v) for k, v in st.items()} if isinstance(st, dict) else {},
            message_count=int(raw.get("message_count") or 0),
        )

    def to_config_patch(self) -> dict[str, Any]:
        return {
            "lore_state": {
                "cooldown": dict(self.cooldown),
                "sticky": dict(self.sticky),
                "message_count": self.message_count,
            }
        }

    def tick_user_turn(self) -> None:
        self.message_count += 1
        for eid in list(self.cooldown.keys()):
            self.cooldown[eid] = max(0, self.cooldown[eid] - 1)
            if self.cooldown[eid] <= 0:
                del self.cooldown[eid]
        for eid in list(self.sticky.keys()):
            self.sticky[eid] = max(0, self.sticky[eid] - 1)
            if self.sticky[eid] <= 0:
                del self.sticky[eid]

    def is_on_cooldown(self, entry_id: str) -> bool:
        return self.cooldown.get(entry_id, 0) > 0

    def is_sticky_active(self, entry_id: str) -> bool:
        return self.sticky.get(entry_id, 0) > 0

    def apply_activations(self, entries: list[LoreEntry]) -> None:
        for entry in entries:
            if entry.cooldown > 0:
                self.cooldown[entry.id] = entry.cooldown
            if entry.sticky > 0:
                self.sticky[entry.id] = entry.sticky

    @staticmethod
    def passes_probability(entry: LoreEntry) -> bool:
        prob = max(0.0, min(1.0, float(entry.probability)))
        if prob >= 1.0:
            return True
        if prob <= 0.0:
            return False
        return random.random() <= prob
