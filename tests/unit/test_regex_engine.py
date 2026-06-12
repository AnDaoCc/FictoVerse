from __future__ import annotations

from novel_world.modules.ai.domain.regex_script import PLACEMENT_AI_OUTPUT, PLACEMENT_USER_INPUT, RegexScript
from novel_world.modules.ai.services.regex_engine import RegexEngine


def test_user_input_stage() -> None:
    engine = RegexEngine(
        [
            RegexScript(
                id="1",
                find_regex="hello",
                replace_string="hi",
                placement=[PLACEMENT_USER_INPUT],
            )
        ]
    )
    assert engine.apply_user_input("say hello") == "say hi"


def test_depth_filter() -> None:
    engine = RegexEngine(
        [
            RegexScript(
                id="1",
                find_regex="x",
                replace_string="y",
                placement=[PLACEMENT_AI_OUTPUT],
                min_depth=2,
                max_depth=5,
            )
        ]
    )
    assert engine.apply_ai_output("x", depth=1) == "x"
    assert engine.apply_ai_output("x", depth=3) == "y"
