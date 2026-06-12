from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from novel_world.modules.ai.services.lore_session_state import LoreSessionState
from novel_world.modules.world.domain.lore_entry import LoreEntry
from novel_world.modules.world.services.st_lore_codec import parse_st_world_info


@dataclass
class LoreSegment:
    position: str
    content: str
    depth: int = 4
    entry_id: str = ""
    keys: list[str] = field(default_factory=list)


@dataclass
class LoreResult:
    before_main: list[str] = field(default_factory=list)
    after_char: list[str] = field(default_factory=list)
    before_examples: list[str] = field(default_factory=list)
    at_depth: list[LoreSegment] = field(default_factory=list)
    post_history: list[str] = field(default_factory=list)
    matched_ids: list[str] = field(default_factory=list)

    def append_text(self, position: str, text: str, entry: LoreEntry) -> None:
        if position == "after_char":
            self.after_char.append(text)
        elif position == "before_examples":
            self.before_examples.append(text)
        elif position == "at_depth":
            self.at_depth.append(
                LoreSegment(position=position, content=text, depth=entry.depth, entry_id=entry.id, keys=entry.keys)
            )
        elif position == "post_history":
            self.post_history.append(text)
        else:
            self.before_main.append(text)
        if entry.id not in self.matched_ids:
            self.matched_ids.append(entry.id)

    def all_text(self) -> str:
        parts = self.before_main + self.after_char + self.before_examples + self.post_history
        parts.extend(seg.content for seg in self.at_depth)
        return "\n\n".join(p for p in parts if p)


class LoreEngine:
    MAX_RECURSIVE_ROUNDS = 2

    def scan(
        self,
        entries: list[LoreEntry],
        scan_text: str,
        *,
        token_budget: int = 2000,
        case_sensitive: bool = False,
        session_state: LoreSessionState | None = None,
        active_character_id: str = "",
        active_character_name: str = "",
        messages: list | None = None,
        user_input: str = "",
        scan_limit: int = 12,
    ) -> LoreResult:
        result = LoreResult()
        if not entries:
            return result

        state = session_state or LoreSessionState()
        enabled = [e for e in entries if e.enabled and self._passes_character_filter(
            e, active_character_id, active_character_name
        )]
        constant = [e for e in enabled if e.constant]
        selective = [e for e in enabled if not e.constant]

        matched: list[LoreEntry] = []
        matched_ids: set[str] = set()

        def _text_for(entry: LoreEntry, pool: str) -> str:
            if messages is not None:
                from novel_world.modules.ai.services.prompt_context import build_scan_text_for_entry

                return build_scan_text_for_entry(
                    messages, user_input, entry, default_limit=scan_limit
                )
            return pool

        for entry in constant:
            if self._should_include(
                entry, _text_for(entry, scan_text), state, case_sensitive, force=True
            ):
                matched.append(entry)
                matched_ids.add(entry.id)

        sticky_candidates = [e for e in selective if state.is_sticky_active(e.id)]
        for entry in sticky_candidates:
            if entry.id not in matched_ids and LoreSessionState.passes_probability(entry):
                matched.append(entry)
                matched_ids.add(entry.id)

        for entry in selective:
            if entry.id in matched_ids:
                continue
            if self._should_include(entry, _text_for(entry, scan_text), state, case_sensitive):
                matched.append(entry)
                matched_ids.add(entry.id)

        scan_pool = scan_text
        for _round in range(self.MAX_RECURSIVE_ROUNDS):
            scan_pool = scan_text + "\n" + "\n".join(e.content for e in matched if e.recursive)
            added = False
            for entry in selective:
                if entry.id in matched_ids:
                    continue
                if self._should_include(entry, _text_for(entry, scan_pool), state, case_sensitive):
                    matched.append(entry)
                    matched_ids.add(entry.id)
                    added = True
            if not added:
                break

        matched = self._apply_group_rules(matched)
        matched.sort(key=lambda e: (-e.priority, e.insertion_order))

        used_tokens = 0
        activated: list[LoreEntry] = []
        for entry in matched:
            est = max(1, len(entry.content) // 2)
            if used_tokens + est > token_budget and not entry.constant:
                continue
            used_tokens += est
            result.append_text(entry.position, entry.content, entry)
            activated.append(entry)

        state.apply_activations(activated)
        return result

    @staticmethod
    def _passes_character_filter(
        entry: LoreEntry,
        character_id: str,
        character_name: str,
    ) -> bool:
        if not entry.character_filter:
            return True
        names = {character_id.strip().lower(), character_name.strip().lower()}
        names.discard("")
        filt = {f.strip().lower() for f in entry.character_filter if f.strip()}
        if not filt:
            return True
        hit = bool(names & filt)
        if entry.filter_type == "exclude":
            return not hit
        return hit

    def _should_include(
        self,
        entry: LoreEntry,
        text: str,
        state: LoreSessionState,
        case_sensitive: bool,
        *,
        force: bool = False,
    ) -> bool:
        if state.is_on_cooldown(entry.id) and not state.is_sticky_active(entry.id):
            return False
        if force or entry.constant:
            return LoreSessionState.passes_probability(entry)
        if state.is_sticky_active(entry.id):
            return LoreSessionState.passes_probability(entry)
        if not self._matches_keywords(entry, text, case_sensitive):
            return False
        return LoreSessionState.passes_probability(entry)

    @staticmethod
    def _key_in_text(key: str, hay: str, *, whole_words: bool, case_sensitive: bool) -> bool:
        if not key:
            return False
        needle = key if case_sensitive else key.lower()
        if whole_words:
            import re

            pattern = r"\b" + re.escape(needle) + r"\b"
            flags = 0 if case_sensitive else re.IGNORECASE
            return bool(re.search(pattern, hay, flags))
        return needle in hay

    @classmethod
    def _matches_keywords(cls, entry: LoreEntry, text: str, case_sensitive: bool) -> bool:
        if not entry.selective and not entry.constant:
            return True
        if entry.constant:
            return True
        primary = entry.keys or []
        secondary = entry.keys_secondary or []
        if not primary and not secondary:
            return False
        hay = text if case_sensitive else text.lower()

        def _any(keys: list[str]) -> bool:
            return any(
                cls._key_in_text(k, hay, whole_words=entry.match_whole_words, case_sensitive=case_sensitive)
                for k in keys
            )

        def _all(keys: list[str]) -> bool:
            return bool(keys) and all(
                cls._key_in_text(k, hay, whole_words=entry.match_whole_words, case_sensitive=case_sensitive)
                for k in keys
            )

        logic = int(entry.selective_logic or 0)
        if logic == 3:
            primary_ok = _all(primary) if primary else True
            secondary_ok = _all(secondary) if secondary else True
            return primary_ok and secondary_ok
        if logic == 0:
            keys = primary + secondary
            return _any(keys)
        if logic == 1:
            keys = primary + secondary
            return not _all(keys)
        if logic == 2:
            keys = primary + secondary
            return not _any(keys)
        return _any(primary + secondary)

    @staticmethod
    def _apply_group_rules(matched: list[LoreEntry]) -> list[LoreEntry]:
        if not matched:
            return matched
        by_group: dict[str, list[LoreEntry]] = {}
        ungrouped: list[LoreEntry] = []
        for entry in matched:
            if entry.lore_group:
                by_group.setdefault(entry.lore_group, []).append(entry)
            else:
                ungrouped.append(entry)

        out = list(ungrouped)
        for _group, items in by_group.items():
            if any(e.group_override for e in items):
                out.extend(items)
                continue
            if len(items) == 1:
                out.append(items[0])
                continue
            if any(e.use_group_scoring for e in items):
                best = max(items, key=lambda e: e.group_weight)
                out.append(best)
            else:
                out.append(max(items, key=lambda e: (e.priority, e.group_weight)))
        return out

    @staticmethod
    def entries_from_character_book(book: dict | list | None, character_id: str) -> list[LoreEntry]:
        if not book:
            return []
        if isinstance(book, dict):
            payload: dict | list = book
        else:
            payload = {"entries": book}
        entries = parse_st_world_info(
            payload,
            scope="character",
            character_id=character_id,
            source="character_book",
        )
        for i, entry in enumerate(entries):
            if not entry.id:
                entry.id = f"cb-{character_id}-{i}"
        return entries

    def merge_entries(
        self,
        db_entries: list[LoreEntry],
        book_entries: list[LoreEntry],
    ) -> list[LoreEntry]:
        db_refs = {e.source_ref for e in db_entries if e.source == "character_book"}
        merged = list(db_entries)
        for be in book_entries:
            if be.source_ref and be.source_ref in db_refs:
                continue
            merged.append(be)
        return merged

    @staticmethod
    def format_result(result: LoreResult) -> dict[str, str]:
        parts: dict[str, str] = {}
        if result.before_main:
            parts["before_main"] = "\n\n".join(result.before_main)
        if result.after_char:
            parts["after_char"] = "\n\n".join(result.after_char)
        if result.before_examples:
            parts["before_examples"] = "\n\n".join(result.before_examples)
        if result.post_history:
            parts["post_history"] = "\n\n".join(result.post_history)
        return parts

    @staticmethod
    def session_lore_from_config(config: dict[str, Any] | None) -> list[LoreEntry]:
        raw = (config or {}).get("session_lore") or []
        if not isinstance(raw, list):
            return []
        out: list[LoreEntry] = []
        for item in raw:
            if isinstance(item, dict):
                entry = LoreEntry.from_dict(item)
                entry.scope = "session"
                entry.source = "session"
                out.append(entry)
        return out
