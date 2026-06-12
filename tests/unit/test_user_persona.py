from __future__ import annotations

from novel_world.modules.ai.services.user_persona import (
    display_name,
    format_persona_for_prompt,
    format_user_transcript_line,
    is_god_mode,
    merge_session_persona,
    normalize_persona,
    persona_from_world_settings,
    store_persona,
)


def test_is_god_mode_when_both_empty() -> None:
    assert is_god_mode({"name": "", "description": ""})
    assert is_god_mode(None)
    assert not is_god_mode({"name": "旅人", "description": ""})
    assert not is_god_mode({"name": "", "description": "旁观者"})


def test_display_name_god_mode() -> None:
    assert display_name({"name": "", "description": ""}) == "你"


def test_display_name_with_name() -> None:
    assert display_name({"name": "王海", "description": "侦探"}) == "王海"


def test_format_persona_for_prompt_god_mode() -> None:
    text = format_persona_for_prompt({"name": "", "description": ""}, mode="group")
    assert "上帝" in text


def test_format_user_transcript_line() -> None:
    god = format_user_transcript_line({"name": "", "description": ""}, "你好")
    assert "上帝视角" in god
    named = format_user_transcript_line({"name": "甲", "description": ""}, "你好")
    assert named.startswith("甲（用户扮演）")


def test_merge_session_persona_prefers_session() -> None:
    session = {"user_persona": {"name": "会话身份", "description": ""}}
    world = {"user_persona": {"name": "世界默认", "description": "x"}}
    assert merge_session_persona(session, world)["name"] == "会话身份"


def test_merge_session_persona_falls_back_to_world() -> None:
    world = {"user_persona": {"name": "世界默认", "description": ""}}
    assert merge_session_persona({}, world)["name"] == "世界默认"


def test_store_persona_strips() -> None:
    p = store_persona(" 甲 ", " 描述 ")
    assert p == {"name": "甲", "description": "描述"}


def test_persona_from_world_settings() -> None:
    p = persona_from_world_settings({"user_persona": {"name": "默认", "description": ""}})
    assert normalize_persona(p)["name"] == "默认"
