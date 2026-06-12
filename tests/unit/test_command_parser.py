from __future__ import annotations

from dataclasses import dataclass

from novel_world.modules.ai.services.command_parser import parse_at_mention


@dataclass
class _Member:
    character_id: str
    character_name: str


def test_parse_at_mention_by_name() -> None:
    members = [
        _Member("c1", "甲角色"),
        _Member("c2", "乙角色"),
    ]
    text, force_id = parse_at_mention("@甲角色 你好", members)
    assert text == "你好"
    assert force_id == "c1"


def test_parse_at_mention_by_id() -> None:
    members = [_Member("c1", "甲角色")]
    text, force_id = parse_at_mention("@c1 接话", members)
    assert text == "接话"
    assert force_id == "c1"


def test_parse_at_mention_no_match() -> None:
    members = [_Member("c1", "甲角色")]
    original = "@未知 你好"
    text, force_id = parse_at_mention(original, members)
    assert text == original
    assert force_id is None


def test_parse_at_mention_only_mention() -> None:
    members = [_Member("c1", "甲角色")]
    text, force_id = parse_at_mention("@甲角色", members)
    assert text == ""
    assert force_id == "c1"


def test_parse_at_mention_mid_message() -> None:
    members = [
        _Member("c1", "淡然崎"),
        _Member("c2", "王海峰"),
    ]
    text, force_id = parse_at_mention("我想问@淡然崎 你们的世界", members)
    assert text == "我想问 你们的世界"
    assert force_id == "c1"
