from novel_world.modules.stscript.engine import STScriptEngine, parse_st_scripts_json
from novel_world.modules.stscript.runtime import STScriptRuntime


def test_runtime_setvar_getvar() -> None:
    rt = STScriptRuntime()
    rt.run_command_line("/setvar global count 5", input_text="")
    out = rt.run_command_line("/getvar count", input_text="")
    assert out == "5"


def test_engine_send_event() -> None:
    scripts = parse_st_scripts_json(
        [{"name": "upper", "content": '/echo {{input}}', "triggers": ["send"]}]
    )
    engine = STScriptEngine(scripts)
    assert "hello" in engine.apply_event("send", "hello")
