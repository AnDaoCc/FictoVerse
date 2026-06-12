"""SillyTavern Regex Scripts JSON 编解码。"""
from __future__ import annotations

import json
import uuid
from typing import Any

from novel_world.core.exceptions import ValidationError
from novel_world.modules.ai.domain.regex_script import RegexScript


def parse_st_regex_scripts(data: bytes | list | dict) -> list[RegexScript]:
    if isinstance(data, (bytes, bytearray)):
        try:
            raw = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValidationError(f"Regex JSON 无效：{exc}") from exc
    else:
        raw = data

    items: list[Any]
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        if "scripts" in raw and isinstance(raw["scripts"], list):
            items = raw["scripts"]
        else:
            items = list(raw.values())
    else:
        raise ValidationError("Regex JSON 必须是数组或对象。")

    out: list[RegexScript] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        script = RegexScript.from_dict(item, script_id=str(uuid.uuid4()))
        if script.find_regex:
            out.append(script)
    return out


def export_st_regex_scripts(scripts: list[RegexScript]) -> list[dict[str, Any]]:
    return [s.to_dict() for s in scripts if not s.disabled or s.find_regex]
