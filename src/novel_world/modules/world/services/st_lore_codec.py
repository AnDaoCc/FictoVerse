"""SillyTavern World Info / character_book 条目编解码。"""
from __future__ import annotations

import json
import re
from typing import Any

from novel_world.core.exceptions import ValidationError
from novel_world.infrastructure.repositories.sqlite_lore_repository import new_lore_entry_id
from novel_world.modules.world.domain.lore_entry import LoreEntry, LorePosition

_ST_POSITION_MAP: dict[int | str, LorePosition] = {
    0: "before_main",
    1: "after_char",
    2: "before_main",
    3: "before_examples",
    4: "at_depth",
    5: "post_history",
    6: "post_history",
    "before_main": "before_main",
    "after_char": "after_char",
    "before_examples": "before_examples",
    "at_depth": "at_depth",
    "post_history": "post_history",
}


def _parse_key_list(raw: Any) -> list[str]:
    keys: list[str] = []
    if raw is None:
        return keys
    if isinstance(raw, str):
        keys.extend(k.strip() for k in re.split(r"[,，]", raw) if k.strip())
    elif isinstance(raw, list):
        keys.extend(str(k).strip() for k in raw if str(k).strip())
    seen: set[str] = set()
    out: list[str] = []
    for k in keys:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


def _normalize_keys(item: dict[str, Any]) -> list[str]:
    keys = _parse_key_list(item.get("keys"))
    if not keys:
        keys = _parse_key_list(item.get("key"))
    return keys


def _normalize_keys_secondary(item: dict[str, Any]) -> list[str]:
    return _parse_key_list(item.get("keysecondary") or item.get("keys_secondary"))


def _parse_character_filter(item: dict[str, Any]) -> tuple[list[str], str]:
    raw = item.get("characterFilter") or item.get("character_filter")
    if raw is None:
        return [], "include"
    if isinstance(raw, dict):
        names = raw.get("names") or raw.get("characters") or []
        is_exclude = bool(raw.get("isExclude") or raw.get("exclude"))
        if isinstance(names, list):
            return [str(x).strip() for x in names if str(x).strip()], "exclude" if is_exclude else "include"
        return [], "include"
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()], "include"
    if isinstance(raw, str) and raw.strip():
        return [x.strip() for x in re.split(r"[,，]", raw) if x.strip()], "include"
    return [], "include"


def _parse_position(raw: Any) -> LorePosition:
    if isinstance(raw, int) or (isinstance(raw, str) and raw.isdigit()):
        return _ST_POSITION_MAP.get(int(raw), "before_main")
    text = str(raw or "before_main").strip()
    return _ST_POSITION_MAP.get(text, "before_main")  # type: ignore[return-value]


def _parse_recursive(item: dict[str, Any]) -> bool:
    ext = item.get("extensions")
    if isinstance(ext, dict) and "recursive" in ext:
        return bool(ext.get("recursive"))
    return bool(item.get("recursive", False))


def _parse_enabled(item: dict[str, Any]) -> bool:
    if "disable" in item:
        return not bool(item.get("disable"))
    if "enabled" in item:
        return bool(item.get("enabled"))
    return True


def _parse_probability(item: dict[str, Any]) -> float:
    raw = item.get("probability")
    if raw is None:
        return 1.0
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return 1.0
    if val > 1.0:
        val = val / 100.0
    return max(0.0, min(1.0, val))


def _iter_st_entry_items(book: dict | list | None) -> list[tuple[int, dict[str, Any]]]:
    if not book:
        return []
    entries_data: Any
    if isinstance(book, dict):
        entries_data = book.get("entries") or book.get("entry_list") or []
    elif isinstance(book, list):
        entries_data = book
    else:
        return []

    items: list[tuple[int, dict[str, Any]]] = []
    if isinstance(entries_data, dict):
        for idx, key in enumerate(sorted(entries_data.keys(), key=lambda k: int(k) if str(k).isdigit() else str(k))):
            item = entries_data[key]
            if isinstance(item, dict):
                items.append((idx, item))
    elif isinstance(entries_data, list):
        for idx, item in enumerate(entries_data):
            if isinstance(item, dict):
                items.append((idx, item))
    return items


def parse_st_entry_item(
    item: dict[str, Any],
    *,
    index: int,
    scope: str = "world",
    character_id: str = "",
    source: str = "st_import",
) -> LoreEntry | None:
    content = str(item.get("content", "")).strip()
    if not content:
        return None
    keys = _normalize_keys(item)
    keys_secondary = _normalize_keys_secondary(item)
    source_ref = str(item.get("uid") or item.get("id") or index)
    char_filter, filter_type = _parse_character_filter(item)
    ext = item.get("extensions") if isinstance(item.get("extensions"), dict) else {}
    return LoreEntry(
        id=new_lore_entry_id(),
        scope=scope if scope in ("world", "character", "session") else "world",  # type: ignore[arg-type]
        character_id=character_id.strip(),
        keys=keys,
        keys_secondary=keys_secondary,
        selective_logic=int(item.get("selectiveLogic") or item.get("selective_logic") or 0),
        match_whole_words=bool(item.get("matchWholeWords") or item.get("match_whole_words", False)),
        use_vector=bool(item.get("vectorized") or item.get("use_vector", False)),
        vectorized=bool(item.get("vectorized", False)),
        content=content,
        constant=bool(item.get("constant", False)),
        selective=bool(item.get("selective", True)),
        recursive=_parse_recursive(item),
        priority=int(item.get("priority", item.get("order", 0)) or 0),
        insertion_order=int(item.get("insertion_order", item.get("order", index)) or index),
        position=_parse_position(item.get("position", "before_main")),
        depth=int(item.get("depth", 4) or 4),
        enabled=_parse_enabled(item),
        comment=str(item.get("comment", "")),
        source=source,  # type: ignore[arg-type]
        source_ref=source_ref,
        probability=_parse_probability(item),
        lore_group=str(item.get("group") or item.get("lore_group") or ""),
        group_override=bool(item.get("groupOverride") or item.get("group_override", False)),
        group_weight=int(item.get("groupWeight") or item.get("group_weight") or 100),
        cooldown=int(item.get("cooldown") or 0),
        sticky=int(item.get("sticky") or 0),
        character_filter=char_filter,
        filter_type=filter_type,  # type: ignore[arg-type]
        scan_depth=int(item.get("scanDepth") or item.get("scan_depth") or ext.get("scan_depth") or 0),
        use_group_scoring=bool(item.get("useGroupScoring") or item.get("use_group_scoring", False)),
    )


def parse_st_world_info(
    raw: dict[str, Any] | list[Any],
    *,
    scope: str = "world",
    character_id: str = "",
    source: str = "st_import",
) -> list[LoreEntry]:
    if isinstance(raw, list):
        book: dict | list = raw
    elif isinstance(raw, dict):
        book = raw
    else:
        raise ValidationError("World Info JSON 必须是对象或数组。")

    out: list[LoreEntry] = []
    for idx, item in _iter_st_entry_items(book if isinstance(book, (dict, list)) else {}):
        entry = parse_st_entry_item(
            item,
            index=idx,
            scope=scope,
            character_id=character_id,
            source=source,
        )
        if entry is not None:
            out.append(entry)
    return out


def parse_st_world_info_bytes(data: bytes) -> dict[str, Any] | list[Any]:
    try:
        parsed = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"World Info JSON 无效：{exc}") from exc
    if not isinstance(parsed, (dict, list)):
        raise ValidationError("World Info JSON 根节点必须是对象或数组。")
    return parsed


def _position_to_st(position: str) -> int:
    mapping = {
        "before_main": 0,
        "after_char": 1,
        "before_examples": 3,
        "at_depth": 4,
        "post_history": 5,
    }
    return mapping.get(position, 0)


def export_st_entry_dict(entry: LoreEntry) -> dict[str, Any]:
    keys = entry.keys or []
    primary = keys[0] if keys else ""
    secondary = entry.keys_secondary or (keys[1:] if len(keys) > 1 else [])
    out: dict[str, Any] = {
        "uid": entry.source_ref or entry.id,
        "key": primary,
        "keysecondary": secondary,
        "keys": keys,
        "selectiveLogic": entry.selective_logic,
        "matchWholeWords": entry.match_whole_words,
        "vectorized": entry.vectorized or entry.use_vector,
        "content": entry.content,
        "constant": entry.constant,
        "selective": entry.selective,
        "extensions": {"recursive": entry.recursive},
        "priority": entry.priority,
        "order": entry.insertion_order,
        "position": _position_to_st(entry.position),
        "depth": entry.depth,
        "disable": not entry.enabled,
        "comment": entry.comment,
        "probability": entry.probability,
        "group": entry.lore_group,
        "groupOverride": entry.group_override,
        "groupWeight": entry.group_weight,
        "cooldown": entry.cooldown,
        "sticky": entry.sticky,
        "scanDepth": entry.scan_depth,
        "useGroupScoring": entry.use_group_scoring,
    }
    if entry.character_filter:
        if entry.filter_type == "exclude":
            out["characterFilter"] = {"names": entry.character_filter, "isExclude": True}
        else:
            out["characterFilter"] = entry.character_filter
    return out


def export_st_world_info(entries: list[LoreEntry]) -> dict[str, Any]:
    sorted_entries = sorted(entries, key=lambda e: (e.insertion_order, e.priority))
    out_entries: dict[str, Any] = {}
    for idx, entry in enumerate(sorted_entries):
        out_entries[str(idx)] = export_st_entry_dict(entry)
    return {"entries": out_entries}
