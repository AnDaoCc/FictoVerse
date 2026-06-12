from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from novel_world.infrastructure.server_meta import write_server_meta
from novel_world.launcher import bootstrap
from novel_world.launcher import gui


def _write_minimal_venv(root: Path) -> None:
    venv_scripts = root / ".venv" / "Scripts"
    venv_scripts.mkdir(parents=True)
    (venv_scripts / "python.exe").write_text("", encoding="utf-8")
    (root / ".venv" / "pyvenv.cfg").write_text("home = C:\\Python311\n", encoding="utf-8")


def test_deps_need_install_when_no_sentinel(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    _write_minimal_venv(root)

    monkeypatch.setattr(bootstrap, "get_root", lambda: root)
    assert bootstrap.deps_need_install(root) is True


def test_deps_skip_when_sentinel_matches(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    pyproject = root / "pyproject.toml"
    pyproject.write_text("[project]\nname='x'\n", encoding="utf-8")
    _write_minimal_venv(root)
    mtime = pyproject.stat().st_mtime
    (root / ".venv" / bootstrap.DEPS_SENTINEL).write_text(str(mtime), encoding="utf-8")

    monkeypatch.setattr(bootstrap, "get_root", lambda: root)
    assert bootstrap.deps_need_install(root) is False


def test_get_status_not_running_without_meta(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "proj"
    (root / "data").mkdir(parents=True)
    monkeypatch.setattr(bootstrap, "get_root", lambda: root)
    monkeypatch.setattr(
        bootstrap,
        "default_config",
        lambda r=None: type("C", (), {"data_dir": root / "data"})(),
    )
    status = bootstrap.get_status(root)
    assert status.running is False
    assert "未运行" in status.message


def test_get_status_running_with_alive_pid(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "proj"
    data_dir = root / "data"
    data_dir.mkdir(parents=True)
    monkeypatch.setattr(bootstrap, "get_root", lambda: root)
    monkeypatch.setattr(
        bootstrap,
        "default_config",
        lambda r=None: type("C", (), {"data_dir": data_dir})(),
    )
    write_server_meta(data_dir, host="127.0.0.1", port=9999)
    meta_path = data_dir / "server.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["pid"] = 999999
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    monkeypatch.setattr(bootstrap, "_http_ready", lambda h, p: True)
    monkeypatch.setattr(bootstrap, "_pid_alive", lambda pid: True)

    status = bootstrap.get_status(root)
    assert status.running is True
    assert status.port == 9999
    assert "chat" in status.url


def test_resolve_project_root_from_env(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    monkeypatch.setenv("NOVEL_WORLD_ROOT", str(root))
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert bootstrap.resolve_project_root() == root.resolve()


def test_resolve_project_root_frozen_next_to_pyproject(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    exe_dir = root / "dist"
    exe_dir.mkdir()
    fake_exe = exe_dir / "launcher.exe"
    fake_exe.write_text("", encoding="utf-8")
    monkeypatch.delenv("NOVEL_WORLD_ROOT", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe), raising=False)
    assert bootstrap.resolve_project_root() == root.resolve()


def test_resolve_project_root_frozen_missing_pyproject(tmp_path: Path, monkeypatch) -> None:
    exe_dir = tmp_path / "alone"
    exe_dir.mkdir()
    fake_exe = exe_dir / "launcher.exe"
    fake_exe.write_text("", encoding="utf-8")
    monkeypatch.delenv("NOVEL_WORLD_ROOT", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe), raising=False)
    try:
        bootstrap.resolve_project_root()
        assert False, "expected ProjectRootNotFoundError"
    except bootstrap.ProjectRootNotFoundError:
        pass


def test_get_system_info_includes_versions(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "pyproject.toml").write_text(
        '[project]\nname="x"\nversion="0.2.0"\n',
        encoding="utf-8",
    )
    (root / "data").mkdir()
    monkeypatch.setattr(bootstrap, "get_root", lambda: root)
    info = bootstrap.get_system_info(root)
    assert info["app_version"] == "0.2.0"
    assert info["launcher_version"] == bootstrap.LAUNCHER_VERSION
    assert info["root_ok"] is True


def test_launch_calls_install_then_start(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    calls: list[str] = []

    monkeypatch.setattr(bootstrap, "get_root", lambda: root)
    monkeypatch.setattr(bootstrap, "venv_python", lambda r=None: root / ".venv" / "Scripts" / "python.exe")
    monkeypatch.setattr(bootstrap, "_verify_web_import", lambda py, r: (True, ""))
    monkeypatch.setattr(
        bootstrap,
        "install_deps",
        lambda *a, **k: (calls.append("install"), True, "ok")[1:],
    )
    monkeypatch.setattr(
        bootstrap,
        "start_server",
        lambda *a, **k: (calls.append("start"), True, "http://127.0.0.1/chat")[1:],
    )
    monkeypatch.setattr(
        bootstrap,
        "open_browser",
        lambda *a, **k: (calls.append("browser"), True, "opened")[1:],
    )

    ok, _msg = bootstrap.launch(root, open_after=True)
    assert ok is True
    assert calls == ["install", "start", "browser"]


def test_launch_fails_fast_when_verify_fails(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    started: list[str] = []

    monkeypatch.setattr(bootstrap, "get_root", lambda: root)
    monkeypatch.setattr(bootstrap, "venv_python", lambda r=None: root / ".venv" / "Scripts" / "python.exe")
    monkeypatch.setattr(
        bootstrap,
        "install_deps",
        lambda *a, **k: (True, "ok"),
    )
    monkeypatch.setattr(
        bootstrap,
        "_verify_web_import",
        lambda py, r: (False, "No module named novel_world"),
    )
    monkeypatch.setattr(
        bootstrap,
        "start_server",
        lambda *a, **k: (started.append("start"), True, "url")[1:],
    )

    ok, msg = bootstrap.launch(root, open_after=False)
    assert ok is False
    assert "novel_world" in msg
    assert started == []


def test_pid_alive_invalid_pid_returns_false() -> None:
    assert bootstrap._pid_alive(0) is False
    assert bootstrap._pid_alive(-1) is False
    assert bootstrap._pid_state(0) == "dead"


def test_pid_alive_does_not_raise_system_error(monkeypatch) -> None:
    def _boom(_pid: int) -> str:
        raise SystemError("<built-in function kill> returned a result with an exception set")

    monkeypatch.setattr(bootstrap, "_pid_state", _boom)
    try:
        bootstrap._pid_alive(12345)
    except SystemError:
        assert False, "_pid_alive must not propagate SystemError"


def test_get_status_running_when_http_ready_despite_pid_error(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "proj"
    data_dir = root / "data"
    data_dir.mkdir(parents=True)
    monkeypatch.setattr(bootstrap, "get_root", lambda: root)
    monkeypatch.setattr(
        bootstrap,
        "read_server_meta",
        lambda _d: {"host": "127.0.0.1", "port": 18080, "pid": 99999},
    )
    monkeypatch.setattr(bootstrap, "_http_ready", lambda h, p: True)
    monkeypatch.setattr(
        bootstrap,
        "_pid_state",
        lambda _pid: (_ for _ in ()).throw(SystemError("kill failed")),
    )

    status = bootstrap.get_status(root)
    assert status.running is True
    assert status.port == 18080
    assert "18080" in status.url


def test_resolve_ui_dir_dev() -> None:
    ui = gui.resolve_ui_dir()
    assert (ui / "index.html").is_file()


def test_resolve_ui_dir_frozen_meipass(tmp_path: Path, monkeypatch) -> None:
    ui_root = tmp_path / "novel_world" / "launcher" / "ui"
    ui_root.mkdir(parents=True)
    (ui_root / "index.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    ui = gui.resolve_ui_dir()
    assert ui == ui_root
    assert (ui / "index.html").is_file()


def test_python_for_venv_dev_uses_sys_executable(monkeypatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert bootstrap.python_for_venv() == Path(sys.executable).resolve()


def test_python_for_venv_frozen_requires_system_python(monkeypatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(bootstrap, "find_system_python", lambda: None)
    try:
        bootstrap.python_for_venv()
        assert False, "expected PythonNotFoundError"
    except bootstrap.PythonNotFoundError:
        pass


def test_python_for_venv_frozen_uses_system_python(tmp_path: Path, monkeypatch) -> None:
    fake_py = tmp_path / "python.exe"
    fake_py.write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(bootstrap, "find_system_python", lambda: fake_py)
    assert bootstrap.python_for_venv() == fake_py


def test_is_venv_valid_requires_pyvenv_cfg(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    monkeypatch.setattr(bootstrap, "get_root", lambda: root)
    scripts = root / ".venv" / "Scripts"
    scripts.mkdir(parents=True)
    (scripts / "python.exe").write_text("", encoding="utf-8")
    assert bootstrap.is_venv_valid(root) is False
    (root / ".venv" / "pyvenv.cfg").write_text("home = C:\\Python311\n", encoding="utf-8")
    assert bootstrap.is_venv_valid(root) is True


def test_ensure_venv_rebuilds_broken_venv(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    scripts = root / ".venv" / "Scripts"
    scripts.mkdir(parents=True)
    (scripts / "pythonw.exe").write_text("", encoding="utf-8")

    base_py = root / "base_python.exe"
    base_py.write_text("", encoding="utf-8")
    created: list[str] = []

    def fake_run(cmd, **kwargs):
        created.append(cmd[3])
        _write_minimal_venv(root)

    monkeypatch.setattr(bootstrap, "get_root", lambda: root)
    monkeypatch.setattr(bootstrap, "python_for_venv", lambda: base_py)
    monkeypatch.setattr(bootstrap, "subprocess", type("S", (), {"run": staticmethod(fake_run)})())

    py = bootstrap.ensure_venv(root)
    assert py == root / ".venv" / "Scripts" / "python.exe"
    assert bootstrap.is_venv_valid(root)
    assert created == [str(root / ".venv")]


def test_check_prerequisites_no_venv(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    monkeypatch.setattr(bootstrap, "get_root", lambda: root)
    monkeypatch.setattr(bootstrap, "find_system_python", lambda: root / "py.exe")
    monkeypatch.setattr(bootstrap, "_query_python_version", lambda _p: (3, 12, 0))
    monkeypatch.setattr(bootstrap, "check_webview2", lambda: True)

    pre = bootstrap.check_prerequisites(root)
    assert pre["root_ok"] is True
    assert pre["python_ok"] is True
    assert pre["venv_exists"] is False
    assert pre["ready"] is False


def test_pip_subprocess_env_clears_proxy_and_sets_utf8(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    env = bootstrap._pip_subprocess_env(root)
    assert env["PYTHONUTF8"] == "1"
    assert env["HTTP_PROXY"] == ""
    assert env["PIP_DEFAULT_TIMEOUT"] == "120"
    assert env["NOVEL_WORLD_ROOT"] == str(root)


def test_pip_default_args_include_mirror_and_empty_proxy() -> None:
    args = bootstrap._pip_default_args()
    assert "--proxy" in args
    assert args[args.index("--proxy") + 1] == ""
    assert "pypi.tuna.tsinghua.edu.cn" in args


def test_pip_build_command_places_mirror_after_subcommand() -> None:
    py = Path("python.exe")
    cmd = bootstrap._pip_build_command(py, ["install", "-U", "pip"])
    assert cmd[:4] == ["python.exe", "-m", "pip", "install"]
    assert cmd[4:6] == ["--proxy", ""]
    assert "pypi.tuna.tsinghua.edu.cn" in cmd
    assert cmd[-2:] == ["-U", "pip"]


def test_decode_bytes_falls_back_for_gbk() -> None:
    raw = "小说世界书".encode("gbk")
    text = bootstrap._decode_bytes(raw)
    assert "小说" in text


def test_install_environment_offline_fallback_on_pip_failure(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    py = root / ".venv" / "Scripts" / "python.exe"
    py.parent.mkdir(parents=True)
    py.write_text("", encoding="utf-8")

    pip_calls = 0

    def fake_pip(py_path, r, args, log):
        nonlocal pip_calls
        pip_calls += 1
        if pip_calls == 2:
            return False, "online failed"
        return True, "ok"

    monkeypatch.setattr(bootstrap, "get_root", lambda: root)
    monkeypatch.setattr(bootstrap, "python_for_venv", lambda: root / "sys_python.exe")
    monkeypatch.setattr(bootstrap, "ensure_venv", lambda *a, **k: py)
    monkeypatch.setattr(bootstrap, "_pip_run", fake_pip)
    monkeypatch.setattr(bootstrap, "_write_sentinel_mtime", lambda r: None)
    monkeypatch.setattr(
        bootstrap,
        "subprocess",
        type(
            "S",
            (),
            {
                "run": staticmethod(
                    lambda *a, **k: type("P", (), {"returncode": 0, "stdout": b"", "stderr": b""})()
                ),
                "CalledProcessError": subprocess.CalledProcessError,
                "TimeoutExpired": subprocess.TimeoutExpired,
            },
        ),
    )
    monkeypatch.setattr(
        "novel_world.launcher.deps_install.install_environment_offline_fallback",
        lambda *a, **k: (True, "offline ok"),
    )

    ok, msg = bootstrap.install_environment(root, force=True)
    assert ok is True
    assert "完成" in msg
    assert pip_calls >= 2


def test_install_environment_calls_steps_in_order(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    calls: list[str] = []

    monkeypatch.setattr(bootstrap, "get_root", lambda: root)
    monkeypatch.setattr(bootstrap, "python_for_venv", lambda: root / "sys_python.exe")
    monkeypatch.setattr(
        bootstrap,
        "ensure_venv",
        lambda *a, **k: (calls.append("venv"), root / ".venv" / "Scripts" / "python.exe")[1],
    )
    monkeypatch.setattr(
        bootstrap,
        "_pip_run",
        lambda py, r, args, log: (calls.append("pip:" + " ".join(args)), True, "ok")[1:],
    )
    monkeypatch.setattr(bootstrap, "_write_sentinel_mtime", lambda r: calls.append("sentinel"))
    monkeypatch.setattr(
        bootstrap,
        "subprocess",
        type(
            "S",
            (),
            {
                "run": staticmethod(
                    lambda *a, **k: type(
                        "P", (), {"returncode": 0, "stdout": "", "stderr": ""}
                    )()
                ),
                "CalledProcessError": subprocess.CalledProcessError,
                "TimeoutExpired": subprocess.TimeoutExpired,
            },
        ),
    )

    ok, _msg = bootstrap.install_environment(root, force=True)
    assert ok is True
    assert calls[0] == "venv"
    assert any(c.startswith("pip:install -U pip") for c in calls)
    assert any("pip:install -e" in c for c in calls)
    assert "sentinel" in calls
