from __future__ import annotations

import json

from novel_world.modules.ai.domain.regex_script import PLACEMENT_USER_INPUT
from novel_world.modules.ai.services.st_regex_codec import parse_st_regex_scripts


def test_parse_st_regex_array() -> None:
    raw = [
        {
            "scriptName": "trim spaces",
            "findRegex": "\\s+",
            "replaceString": " ",
            "placement": [PLACEMENT_USER_INPUT],
            "minDepth": 1,
            "maxDepth": 10,
            "markdownOnly": True,
        }
    ]
    scripts = parse_st_regex_scripts(raw)
    assert len(scripts) == 1
    assert scripts[0].script_name == "trim spaces"
    assert scripts[0].min_depth == 1
    assert scripts[0].markdown_only is True


def test_parse_st_regex_from_bytes() -> None:
    data = json.dumps({"scripts": [{"scriptName": "x", "findRegex": "a", "replaceString": "b", "placement": [2]}]}).encode()
    scripts = parse_st_regex_scripts(data)
    assert len(scripts) == 1
