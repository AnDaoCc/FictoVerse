from __future__ import annotations

from novel_world.modules.ai.domain.prompt_slots import PromptProfile, PromptSlot
from novel_world.modules.ai.services.prompt_macros import MacroContext, apply_macros
from novel_world.modules.ai.services.st_preset_codec import parse_st_preset


def test_prompt_profile_order() -> None:
    profile = PromptProfile(
        slots=[
            PromptSlot("main", "MAIN"),
            PromptSlot("jailbreak", "JB"),
        ],
        order=["jailbreak", "main"],
    )
    layers = profile.to_layers()
    assert layers.jailbreak == "JB"
    assert layers.main == "MAIN"


def test_preset_prompt_order() -> None:
    preset = parse_st_preset(
        {
            "temperature": 0.7,
            "prompts": [
                {"identifier": "main", "content": "Main text"},
                {"identifier": "jailbreak", "content": "JB text"},
            ],
            "prompt_order": ["jailbreak", "main"],
        }
    )
    assert preset["prompt_profile"]["order"] == ["jailbreak", "main"]


def test_build_from_profile_order() -> None:
    from novel_world.modules.ai.services.prompt_assembler import PromptAssembler

    profile = PromptProfile(
        slots=[
            PromptSlot("main", "MAIN"),
            PromptSlot("jailbreak", "JB"),
        ],
        order=["jailbreak", "main"],
    )
    system = PromptAssembler().build_from_profile(profile, [], {})
    assert system.index("JB") < system.index("MAIN")


def test_extended_macros() -> None:
    ctx = MacroContext(lore_text="lore block")
    assert apply_macros("{{lore}} and {{newline}}", ctx) == "lore block and \n"
    roll = apply_macros("{{roll:6}}", ctx)
    assert roll.isdigit() and 1 <= int(roll) <= 6
