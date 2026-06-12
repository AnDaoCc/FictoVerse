from __future__ import annotations

import json

from novel_world.modules.ai.services.st_preset_codec import apply_preset_to_prefs, parse_st_preset


def test_parse_generation_and_layers() -> None:
    raw = {
        "name": "Test Preset",
        "temperature": 0.9,
        "top_p": 0.95,
        "openai_max_tokens": 800,
        "repetition_penalty": 1.1,
        "stop": ["</s>"],
        "prompts": [
            {"identifier": "main", "content": "Main prompt"},
            {"identifier": "jailbreak", "content": "JB one"},
            {"identifier": "nsfw", "content": "JB two"},
            {"identifier": "post_history", "content": "Post hist"},
            {"identifier": "authors_note", "content": "AN text", "depth": 2},
        ],
    }
    preset = parse_st_preset(raw)
    assert preset["name"] == "Test Preset"
    gen = preset["generation"]
    assert gen["temperature"] == 0.9
    assert gen["top_p"] == 0.95
    assert gen["max_tokens"] == 800
    assert gen["repetition_penalty"] == 1.1
    assert gen["stop"] == ["</s>"]

    layers = preset["prompt_layers"]
    assert layers["main"] == "Main prompt"
    assert "JB one" in layers["jailbreak"]
    assert "JB two" in layers["jailbreak"]
    assert layers["post_history"] == "Post hist"
    assert layers["authors_note"]["content"] == "AN text"
    assert layers["authors_note"]["depth"] == 2


def test_apply_preset_to_prefs() -> None:
    preset = parse_st_preset(
        {
            "temperature": 0.5,
            "prompts": [{"name": "main", "content": "hello"}],
        }
    )
    merged = apply_preset_to_prefs({"locale": "zh"}, preset)
    assert merged["locale"] == "zh"
    assert merged["default_generation"]["temperature"] == 0.5
    assert merged["default_prompt_layers"]["main"] == "hello"


def test_parse_from_bytes() -> None:
    data = json.dumps({"temp": 0.7, "prompts": []}).encode("utf-8")
    preset = parse_st_preset(data)
    assert "generation" in preset
