from novel_world.modules.ai.domain.regex_script import PLACEMENT_SLASH_COMMAND, RegexScript
from novel_world.modules.ai.services.regex_engine import RegexEngine


def test_slash_command_placement() -> None:
    engine = RegexEngine(
        [
            RegexScript(
                id="1",
                find_regex="^/test",
                replace_string="/ok",
                placement=[PLACEMENT_SLASH_COMMAND],
            )
        ]
    )
    assert engine.apply_slash_command("/test hello") == "/ok hello"
