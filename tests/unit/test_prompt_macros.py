from __future__ import annotations

from novel_world.modules.ai.services.prompt_macros import MacroContext, apply_macros


def test_basic_macros() -> None:
    ctx = MacroContext(
        char_name="凌筱崎",
        user_name="旅人",
        persona_text="外来调查员",
        description="天才剑修",
        personality="冷静",
        scenario="宗门大比",
        world_name="青云界",
    )
    text = "{{char}} meets {{user}} in {{world}}. {{persona}} / {{description}} / {{personality}} / {{scenario}}"
    out = apply_macros(text, ctx)
    assert "凌筱崎" in out
    assert "旅人" in out
    assert "青云界" in out
    assert "外来调查员" in out
    assert "天才剑修" in out
    assert "冷静" in out
    assert "宗门大比" in out


def test_char_desc_alias() -> None:
    ctx = MacroContext(description="desc body")
    assert apply_macros("{{char_desc}}", ctx) == "desc body"


def test_case_insensitive() -> None:
    ctx = MacroContext(char_name="A", user_name="B")
    assert apply_macros("{{CHAR}} and {{User}}", ctx) == "A and B"


def test_empty_and_unknown() -> None:
    assert apply_macros("", MacroContext(char_name="x")) == ""
    assert apply_macros("{{unknown}}", MacroContext()) == "{{unknown}}"
    assert apply_macros("plain", None) == "plain"
