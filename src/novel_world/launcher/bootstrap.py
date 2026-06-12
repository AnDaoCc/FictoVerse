from __future__ import annotations

import locale
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from novel_world.bootstrap.config import default_config, project_root
from novel_world.infrastructure.server_meta import read_server_meta, remove_server_meta

# ---- launcher config persistence ----
_LAUNCHER_CONFIG_DIR = Path(os.environ.get("APPDATA", os.path.expanduser("~"))) / "FictoVerse"
_LAUNCHER_CONFIG_FILE = _LAUNCHER_CONFIG_DIR / "launcher-config.json"


def load_launcher_config() -> dict[str, Any]:
    """读取启动器配置文件（持久化项目根目录路径等）。"""
    try:
        if _LAUNCHER_CONFIG_FILE.is_file():
            return json.loads(_LAUNCHER_CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def save_launcher_config(data: dict[str, Any]) -> None:
    """保存启动器配置文件。"""
    _LAUNCHER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _LAUNCHER_CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


LAUNCHER_VERSION = "2026-V2"
_ROOT_SEARCH_DEPTH = 4
MIN_PYTHON = (3, 10)
_WEBVIEW2_REG_PATH = r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"

LogCallback = Callable[[str], None]
ProgressCallback = Callable[[str, int, int, str], None]

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
VENV_DIR = ".venv"
DEPS_SENTINEL = ".deps_installed"
STARTUP_TIMEOUT_SEC = 45
POLL_INTERVAL_SEC = 0.2


@dataclass
class ServerStatus:
    running: bool
    url: str = ""
    port: int = 0
    pid: int = 0
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "url": self.url,
            "port": self.port,
            "pid": self.pid,
            "message": self.message,
        }


class ProjectRootNotFoundError(FileNotFoundError):
    """无法定位含 pyproject.toml 的项目根目录。"""


class PythonNotFoundError(RuntimeError):
    """未找到可用于创建虚拟环境的 Python 3.10+。"""


def resolve_project_root() -> Path:
    # 1. Saved config
    config = load_launcher_config()
    saved = config.get("project_root", "").strip()
    if saved:
        path = Path(saved).resolve()
        if (path / "pyproject.toml").is_file():
            os.environ["NOVEL_WORLD_ROOT"] = str(path)
            return path

    # 2. Environment variable
    env_root = os.environ.get("NOVEL_WORLD_ROOT", "").strip()
    if env_root:
        path = Path(env_root).resolve()
        if (path / "pyproject.toml").is_file():
            return path

    # 3. Search nearby (current exe location)
    if getattr(sys, "frozen", False):
        start = Path(sys.executable).resolve().parent
        candidates = [start, *start.parents[:_ROOT_SEARCH_DEPTH]]
        for candidate in candidates:
            if (candidate / "pyproject.toml").is_file():
                return candidate

    # 4. Source development mode
    if not getattr(sys, "frozen", False):
        return project_root()

    # 5. Frozen but nothing found → caller should handle
    raise ProjectRootNotFoundError(
        "请将启动器 exe 放在含 pyproject.toml 的项目根目录（或设置 NOVEL_WORLD_ROOT）。"
    )


def set_and_save_project_root(path: Path) -> None:
    """设置项目根目录并持久化保存。"""
    path = path.resolve()
    if not (path / "pyproject.toml").is_file():
        raise ProjectRootNotFoundError(f"所选目录未找到 pyproject.toml：{path}")
    os.environ["NOVEL_WORLD_ROOT"] = str(path)
    save_launcher_config({"project_root": str(path)})


def get_root() -> Path:
    return resolve_project_root()


def is_frozen_launcher() -> bool:
    return bool(getattr(sys, "frozen", False))


def _version_tuple(major: int, minor: int, micro: int = 0) -> tuple[int, int, int]:
    return major, minor, micro


def _version_ge(version: tuple[int, int, int], minimum: tuple[int, int]) -> bool:
    return (version[0], version[1]) >= minimum


def _query_python_version(py: Path | str) -> tuple[int, int, int] | None:
    try:
        proc = subprocess.run(
            [
                str(py),
                "-c",
                "import sys; print(sys.version_info.major, sys.version_info.minor, sys.version_info.micro)",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if proc.returncode != 0:
            return None
        parts = proc.stdout.strip().split()
        if len(parts) < 2:
            return None
        return _version_tuple(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def _valid_python_executable(path: Path) -> Path | None:
    if not path.is_file():
        return None
    version = _query_python_version(path)
    if version is None or not _version_ge(version, MIN_PYTHON):
        return None
    return path.resolve()


def _resolve_py_launcher(args: list[str]) -> Path | None:
    try:
        proc = subprocess.run(
            [*args, "-c", "import sys; print(sys.executable)"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if proc.returncode != 0:
            return None
        return _valid_python_executable(Path(proc.stdout.strip()))
    except (OSError, subprocess.TimeoutExpired):
        return None


def find_system_python() -> Path | None:
    """从高版本到低版本动态扫描系统 Python 3.10+。"""
    if sys.platform == "win32":
        for ver in ("3.14", "3.13", "3.12", "3.11", "3.10", "3"):
            found = _resolve_py_launcher(["py", f"-{ver}"])
            if found is not None:
                return found

    which_py = shutil.which("python") or shutil.which("python3")
    if which_py:
        found = _valid_python_executable(Path(which_py))
        if found is not None:
            return found

    if sys.platform == "win32":
        local_app = os.environ.get("LOCALAPPDATA", "")
        if local_app:
            programs = Path(local_app) / "Programs" / "Python"
            if programs.is_dir():
                for child in sorted(programs.glob("Python3*"), reverse=True):
                    candidate = child / "python.exe"
                    found = _valid_python_executable(candidate)
                    if found is not None:
                        return found
        programs_x86 = os.environ.get("ProgramFiles", "") and Path(os.environ["ProgramFiles"]) / "Python"
        if programs_x86 and programs_x86.is_dir():
            for child in sorted(programs_x86.glob("Python3*"), reverse=True):
                candidate = child / "python.exe"
                found = _valid_python_executable(candidate)
                if found is not None:
                    return found
    return None


def find_all_compatible_pythons() -> list[dict[str, str]]:
    """返回系统上所有兼容 Python 3.10+ 的路径和版本信息。"""
    found: dict[str, dict[str, str]] = {}

    def _add(py: Path) -> None:
        path_str = str(py.resolve())
        if path_str in found:
            return
        ver = _query_python_version(py)
        if ver is None:
            return
        found[path_str] = {
            "path": path_str,
            "version": f"{ver[0]}.{ver[1]}.{ver[2]}",
            "major_minor": f"{ver[0]}.{ver[1]}",
        }

    if sys.platform == "win32":
        for ver in ("3.14", "3.13", "3.12", "3.11", "3.10", "3"):
            candidate = _resolve_py_launcher(["py", f"-{ver}"])
            if candidate is not None:
                _add(candidate)

    for name in ("python", "python3"):
        which_py = shutil.which(name)
        if which_py:
            candidate = _valid_python_executable(Path(which_py))
            if candidate is not None:
                _add(candidate)

    if sys.platform == "win32":
        local_app = os.environ.get("LOCALAPPDATA", "")
        search_dirs: list[Path] = []
        if local_app:
            p = Path(local_app) / "Programs" / "Python"
            if p.is_dir():
                search_dirs.append(p)
        prog_files = os.environ.get("ProgramFiles", "")
        if prog_files:
            p = Path(prog_files) / "Python"
            if p.is_dir():
                search_dirs.append(p)
        for programs in search_dirs:
            for child in sorted(programs.glob("Python3*"), reverse=True):
                candidate = _valid_python_executable(child / "python.exe")
                if candidate is not None:
                    _add(candidate)

    result = sorted(found.values(), key=lambda x: x["version"], reverse=True)
    return result


def switch_python(python_path: str, root: Path | None = None, log: LogCallback | None = None) -> tuple[bool, str]:
    """将虚拟环境切换到指定的 Python 版本（重建 venv 并重装依赖）。"""
    root = root or get_root()
    py_path = Path(python_path)
    if not py_path.is_file():
        return False, f"Python 路径无效：{python_path}"
    ver = _query_python_version(py_path)
    if ver is None:
        return False, f"无法验证 Python 版本：{python_path}"
    if not _version_ge(ver, MIN_PYTHON):
        return False, f"Python {ver[0]}.{ver[1]} 不满足最低版本要求（3.10+）"

    venv_dir = root / VENV_DIR
    if venv_dir.exists():
        if log:
            log(f"正在删除旧虚拟环境（{venv_dir}）…")
        shutil.rmtree(venv_dir, ignore_errors=True)

    if log:
        log(f"使用 {py_path} ({ver[0]}.{ver[1]}.{ver[2]}) 创建虚拟环境…")
    try:
        subprocess.run(
            [str(py_path), "-m", "venv", str(venv_dir)],
            cwd=root,
            check=True,
            creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except (subprocess.CalledProcessError, OSError) as e:
        return False, f"创建虚拟环境失败：{e}"

    if log:
        log("虚拟环境创建成功，正在安装依赖…")

    py = venv_python(root)
    env = _pip_subprocess_env(root)
    try:
        proc = subprocess.run(
            [str(py), "-m", "pip", "install", "--upgrade", "-e", f"{root}[launcher]"],
            cwd=root,
            env=env,
            capture_output=True,
            timeout=300,
            creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if log:
            text = _decode_subprocess_output(proc)
            for line in text.splitlines():
                if line.strip():
                    log(line)
        if proc.returncode != 0:
            return False, "依赖安装失败，请查看控制台日志"
        _write_sentinel_mtime(root)
        return True, f"已切换到 Python {ver[0]}.{ver[1]}.{ver[2]}，依赖安装完成"
    except subprocess.TimeoutExpired:
        return False, "依赖安装超时"


def python_for_venv() -> Path:
    if is_frozen_launcher():
        found = find_system_python()
        if found is None:
            raise PythonNotFoundError(
                "未检测到 Python 3.10+。请在启动器「环境安装」中安装 Python，"
                "或从 https://www.python.org/downloads/ 手动安装并勾选 Add to PATH。"
            )
        return found
    return Path(sys.executable).resolve()


def check_webview2() -> bool:
    if sys.platform != "win32":
        return True
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _WEBVIEW2_REG_PATH) as key:
            winreg.QueryValueEx(key, "pv")
        return True
    except OSError:
        pass
    pf = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    runtime = Path(pf) / "Microsoft" / "EdgeWebView" / "Application"
    return runtime.is_dir() and any(runtime.glob("msedgewebview2.exe"))


def check_prerequisites(root: Path | None = None) -> dict[str, Any]:
    root_ok = True
    root_error = ""
    try:
        root = root or get_root()
    except ProjectRootNotFoundError as e:
        root = Path.cwd()
        root_ok = False
        root_error = str(e)

    system_py = find_system_python()
    python_version = ""
    if system_py is not None:
        ver = _query_python_version(system_py)
        if ver:
            python_version = f"{ver[0]}.{ver[1]}.{ver[2]}"

    venv_exists = is_venv_valid(root) if root_ok else False
    deps_pending = deps_need_install(root) if root_ok and venv_exists else True

    ready = (
        root_ok
        and system_py is not None
        and venv_exists
        and not deps_pending
    )

    return {
        "python_ok": system_py is not None,
        "python_path": str(system_py) if system_py else "",
        "python_version": python_version,
        "webview2_ok": check_webview2(),
        "root_ok": root_ok,
        "root_error": root_error,
        "venv_exists": venv_exists,
        "deps_need_install": deps_pending if root_ok else True,
        "ready": ready,
    }


def install_python_via_winget(log: LogCallback | None = None) -> tuple[bool, str]:
    """通过 winget 安装最新版 Python（从高版本到低版本尝试）。"""
    if sys.platform != "win32":
        return False, "仅支持在 Windows 上通过 winget 安装 Python。"
    py_ids = ["Python.Python.3.13", "Python.Python.3.12", "Python.Python.3.11"]
    for py_id in py_ids:
        if log:
            log(f"正在通过 winget 安装 {py_id}（可能需要几分钟）…")
        proc = subprocess.run(
            [
                "winget",
                "install",
                "-e",
                "--id",
                py_id,
                "--accept-package-agreements",
                "--accept-source-agreements",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
        )
        if proc.stdout and log:
            for line in proc.stdout.splitlines():
                if line.strip():
                    log(line)
        if proc.stderr and log:
            for line in proc.stderr.splitlines():
                if line.strip():
                    log(line)
        # 验证是否安装成功
        found = find_system_python()
        if found is not None:
            if log:
                log(f"Python 已就绪：{found}")
            return True, str(found)
    manual = (
        "winget 安装未检测到 Python。请手动安装 Python 3.10+："
        "https://www.python.org/downloads/ ，安装时勾选「Add python.exe to PATH」。"
    )
    if log:
        log(manual)
    return False, manual
def _pip_default_args() -> list[str]:
    return [
        "--proxy",
        "",
        "-i",
        "https://pypi.tuna.tsinghua.edu.cn/simple",
        "--trusted-host",
        "pypi.tuna.tsinghua.edu.cn",
        "--trusted-host",
        "files.pythonhosted.org",
    ]


def _pip_subprocess_env(root: Path) -> dict[str, str]:
    env = _child_env(root)
    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        env.pop(key, None)
        env[key] = ""
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8:replace"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    env["PIP_DEFAULT_TIMEOUT"] = "120"
    env["NO_PROXY"] = "*"
    return env


def _decode_bytes(raw: bytes | None) -> str:
    if not raw:
        return ""
    candidates = ["utf-8"]
    preferred = locale.getpreferredencoding(False)
    if preferred and preferred not in candidates:
        candidates.append(preferred)
    if "gbk" not in candidates:
        candidates.append("gbk")
    for encoding in candidates:
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def _decode_subprocess_output(proc: subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes]) -> str:
    stdout = proc.stdout if isinstance(proc.stdout, str) else _decode_bytes(proc.stdout)
    stderr = proc.stderr if isinstance(proc.stderr, str) else _decode_bytes(proc.stderr)
    return "\n".join(line for line in stdout.splitlines() + stderr.splitlines() if line.strip())


def _pip_build_command(py: Path, args: list[str]) -> list[str]:
    """Mirror/proxy flags are install-scoped; they must follow the pip subcommand."""
    if not args:
        return [str(py), "-m", "pip"]
    return [str(py), "-m", "pip", args[0], *_pip_default_args(), *args[1:]]


def _pip_run(py: Path, root: Path, args: list[str], log: LogCallback | None) -> tuple[bool, str]:
    proc = subprocess.run(
        _pip_build_command(py, args),
        cwd=root,
        env=_pip_subprocess_env(root),
        capture_output=True,
        creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    output = _decode_subprocess_output(proc)
    if log and output:
        for line in output.splitlines():
            log(line)
    if proc.returncode != 0:
        err = output or "pip 命令失败"
        return False, err
    return True, output


def _emit_progress(
    progress: ProgressCallback | None,
    phase: str,
    step: int,
    total: int,
    message: str,
    *,
    log: LogCallback | None = None,
) -> None:
    if log:
        log(message)
    if progress:
        progress(phase, step, total, message)


def _verify_web_import(py: Path, root: Path) -> tuple[bool, str]:
    proc = subprocess.run(
        [str(py), "-c", "import novel_world.web.run"],
        cwd=root,
        env=_pip_subprocess_env(root),
        capture_output=True,
        creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    if proc.returncode != 0:
        err = _decode_subprocess_output(proc) or "导入校验失败"
        return False, err
    return True, ""


def _child_env(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["NOVEL_WORLD_ROOT"] = str(root)
    return env


def _server_startup_log(root: Path) -> Path:
    log_dir = root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "server-startup.log"


def install_environment(
    root: Path | None = None,
    log: LogCallback | None = None,
    progress: ProgressCallback | None = None,
    *,
    force: bool = True,
    recreate_venv: bool = False,
    install_python: bool = False,
) -> tuple[bool, str]:
    root = root or get_root()
    total = 4

    if install_python:
        ok, message = install_python_via_winget(log)
        if not ok:
            return False, message

    try:
        python_for_venv()
    except PythonNotFoundError as e:
        if log:
            log(str(e))
        return False, str(e)

    if recreate_venv:
        venv_dir = root / VENV_DIR
        if venv_dir.exists():
            if log:
                log("删除旧虚拟环境…")
            shutil.rmtree(venv_dir, ignore_errors=True)

    _emit_progress(
        progress, "install", 1, total, "[1/4] 创建/检查虚拟环境…", log=log
    )
    try:
        py = ensure_venv(root, log)
    except (subprocess.CalledProcessError, OSError) as e:
        msg = f"创建虚拟环境失败：{e}"
        if log:
            log(msg)
        return False, msg

    _emit_progress(progress, "install", 2, total, "[2/4] 升级 pip…", log=log)
    ok, message = _pip_run(py, root, ["install", "-U", "pip"], log)
    if not ok:
        return False, message

    if force or deps_need_install(root, force=force):
        _emit_progress(
            progress, "install", 3, total, "[3/4] 安装/更新项目依赖（最新）…", log=log
        )
        ok, message = _pip_run(
            py,
            root,
            ["install", "-e", ".[dev,launcher]", "--upgrade"],
            log,
        )
        if not ok:
            from novel_world.launcher.deps_install import install_environment_offline_fallback

            ok, message = install_environment_offline_fallback(
                py,
                root,
                env=_pip_subprocess_env(root),
                log=log,
                pip_run=_pip_run,
            )
            if not ok:
                if log:
                    log(
                        "环境安装失败。可关闭系统代理（127.0.0.1:10808）后重试，"
                        "或手动执行：python -m pip install --proxy \"\" "
                        "-i https://pypi.tuna.tsinghua.edu.cn/simple -e \".[launcher]\""
                    )
                return False, message
        _write_sentinel_mtime(root)
    elif log:
        log("依赖已是最新，跳过安装。")
        _emit_progress(progress, "install", 3, total, "依赖已是最新，跳过安装。", log=None)

    _emit_progress(progress, "install", 4, total, "[4/4] 校验安装…", log=log)
    ok, err = _verify_web_import(py, root)
    if not ok:
        if log:
            log(err)
        return False, err

    msg = "环境安装完成，可以一键启动。"
    if log:
        log(msg)
    _emit_progress(progress, "install", 4, total, msg, log=None)
    return True, msg


def _read_project_version(root: Path) -> str:
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return "未知"
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return "未知"
    match = re.search(r'^version\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    return match.group(1) if match else "未知"


def directory_for_name(root: Path, name: str) -> Path | None:
    config = default_config(root)
    mapping: dict[str, Path] = {
        "root": root,
        "data": config.data_dir,
        "logs": root / "logs",
        "extensions": config.extensions_dir,
        "mods": config.mods_dir,
    }
    return mapping.get(name)


def get_system_info(root: Path | None = None) -> dict[str, Any]:
    try:
        root = root or get_root()
        root_ok = True
        root_error = ""
    except ProjectRootNotFoundError as e:
        root = Path.cwd()
        root_ok = False
        root_error = str(e)

    config = default_config(root) if root_ok else None
    status = get_status(root) if root_ok else ServerStatus(running=False, message=root_error)
    venv_exists = is_venv_valid(root) if root_ok else False
    deps_pending = deps_need_install(root) if root_ok and venv_exists else True

    return {
        "launcher_version": LAUNCHER_VERSION,
        "app_version": _read_project_version(root) if root_ok else "—",
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "root": str(root) if root_ok else "",
        "root_ok": root_ok,
        "root_error": root_error,
        "venv_exists": venv_exists,
        "deps_need_install": deps_pending if root_ok else True,
        "status": status.to_dict(),
        "paths": {
            "root": str(root),
            "data": str(config.data_dir) if config else "",
            "logs": str(root / "logs"),
            "extensions": str(config.extensions_dir) if config else "",
            "mods": str(config.mods_dir) if config else "",
        },
    }


def open_directory(name: str, root: Path | None = None) -> tuple[bool, str]:
    if sys.platform != "win32":
        return False, "仅支持 Windows。"
    root = root or get_root()
    path = directory_for_name(root, name)
    if path is None:
        return False, f"未知目录：{name}"
    path.mkdir(parents=True, exist_ok=True)
    os.startfile(path)  # noqa: S606 — Windows launcher
    return True, f"已打开 {path}"


def launch(
    root: Path | None = None,
    log: LogCallback | None = None,
    progress: ProgressCallback | None = None,
    *,
    open_after: bool = True,
) -> tuple[bool, str]:
    root = root or get_root()
    total = 4

    _emit_progress(progress, "launch", 1, total, "[1/4] 检查依赖…", log=log)
    ok, message = install_deps(root, log=log, progress=progress)
    if not ok:
        return False, message

    py = venv_python(root)
    _emit_progress(progress, "launch", 2, total, "[2/4] 校验 Web 服务模块…", log=log)
    ok, err = _verify_web_import(py, root)
    if not ok:
        hint = (
            f"{err}\n请在「环境安装」页点击「一键安装最新环境」后重试。"
        )
        if log:
            log(hint)
        return False, hint

    _emit_progress(progress, "launch", 3, total, "[3/4] 启动服务…", log=log)
    ok, message = start_server(root, log=log, progress=progress)
    if not ok:
        log_path = _server_startup_log(root)
        hint = f"{message}\n详见日志：{log_path}"
        if log:
            log(hint)
        return False, hint

    if open_after:
        _emit_progress(progress, "launch", 4, total, "[4/4] 打开浏览器…", log=log)
        browser_ok, browser_msg = open_browser(root)
        if log:
            log(browser_msg)
        if not browser_ok:
            return True, message

    _emit_progress(progress, "launch", 4, total, "启动完成", log=log)
    return True, message


def venv_python(root: Path | None = None) -> Path:
    root = root or get_root()
    return root / VENV_DIR / "Scripts" / "python.exe"


def venv_pythonw(root: Path | None = None) -> Path:
    root = root or get_root()
    return root / VENV_DIR / "Scripts" / "pythonw.exe"


def is_venv_valid(root: Path | None = None) -> bool:
    """虚拟环境需同时存在 pyvenv.cfg 与 Scripts/python.exe。"""
    root = root or get_root()
    return (root / VENV_DIR / "pyvenv.cfg").is_file() and venv_python(root).is_file()


def ensure_venv(root: Path | None = None, log: LogCallback | None = None) -> Path:
    root = root or get_root()
    py = venv_python(root)
    if is_venv_valid(root):
        return py
    venv_dir = root / VENV_DIR
    if venv_dir.exists():
        if log:
            log("虚拟环境不完整（缺少 pyvenv.cfg），正在重建…")
        shutil.rmtree(venv_dir, ignore_errors=True)
    if log:
        log("创建虚拟环境…")
    base_py = python_for_venv()
    subprocess.run(
        [str(base_py), "-m", "venv", str(root / VENV_DIR)],
        cwd=root,
        check=True,
        creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    if log:
        log(f"虚拟环境已创建（使用 {base_py}）。")
    return py


def _pyproject_mtime(root: Path) -> float:
    path = root / "pyproject.toml"
    return path.stat().st_mtime if path.exists() else 0.0


def _read_sentinel_mtime(root: Path) -> float | None:
    sentinel = root / VENV_DIR / DEPS_SENTINEL
    if not sentinel.exists():
        return None
    try:
        text = sentinel.read_text(encoding="utf-8").strip()
        return float(text) if text else None
    except ValueError:
        return None


def _write_sentinel_mtime(root: Path) -> None:
    sentinel = root / VENV_DIR / DEPS_SENTINEL
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_text(str(_pyproject_mtime(root)), encoding="utf-8")


def deps_need_install(root: Path | None = None, *, force: bool = False) -> bool:
    if force:
        return True
    root = root or get_root()
    if not is_venv_valid(root):
        return True
    recorded = _read_sentinel_mtime(root)
    if recorded is None:
        return True
    return abs(recorded - _pyproject_mtime(root)) > 0.5


def install_deps(
    root: Path | None = None,
    *,
    force: bool = False,
    log: LogCallback | None = None,
    progress: ProgressCallback | None = None,
) -> tuple[bool, str]:
    root = root or get_root()
    py = ensure_venv(root, log)
    if not deps_need_install(root, force=force):
        msg = "依赖已是最新，跳过安装。"
        _emit_progress(progress, "launch", 1, 4, msg, log=log)
        return True, msg

    _emit_progress(progress, "launch", 1, 4, "[1/4] 安装/更新依赖…", log=log)
    ok, err = _pip_run(py, root, ["install", "-e", ".[dev,launcher]", "--quiet"], log)
    if not ok:
        from novel_world.launcher.deps_install import install_environment_offline_fallback

        ok, err = install_environment_offline_fallback(
            py,
            root,
            env=_pip_subprocess_env(root),
            log=log,
            pip_run=_pip_run,
        )
        if not ok:
            return False, err
    _write_sentinel_mtime(root)
    msg = "依赖安装完成。"
    if log:
        log(msg)
    return True, msg


def _pid_state(pid: int) -> str:
    """返回 alive / dead / unknown。"""
    if pid <= 0:
        return "dead"
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return "unknown"
            try:
                exit_code = wintypes.DWORD()
                if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return "unknown"
                return "alive" if exit_code.value == STILL_ACTIVE else "dead"
            finally:
                kernel32.CloseHandle(handle)
        os.kill(pid, 0)
        return "alive"
    except (OSError, SystemError, ValueError):
        return "dead"


def _pid_alive(pid: int) -> bool:
    try:
        state = _pid_state(pid)
    except (OSError, SystemError, ValueError):
        return True
    if state == "alive":
        return True
    if state == "dead":
        return False
    return True


def _tcp_ready(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.3):
            return True
    except OSError:
        return False


def _probe_http(host: str, port: int) -> tuple[bool, int]:
    if not _tcp_ready(host, port):
        return False, 0
    try:
        with httpx.Client(timeout=2.5, trust_env=False) as client:
            resp = client.get(f"http://{host}:{port}/api/health")
            return resp.status_code == 200, resp.status_code
    except Exception:
        return False, 0


def _http_ready(host: str, port: int) -> bool:
    return _probe_http(host, port)[0]


def get_status(root: Path | None = None) -> ServerStatus:
    root = root or get_root()
    config = default_config(root)
    meta = read_server_meta(config.data_dir)
    if not meta:
        return ServerStatus(running=False, message="未运行")

    host = str(meta.get("host") or "127.0.0.1")
    port = int(meta.get("port") or 0)
    pid = int(meta.get("pid") or 0)
    url = f"http://{host}:{port}/chat" if port else ""

    if port and _http_ready(host, port):
        return ServerStatus(
            running=True,
            url=url,
            port=port,
            pid=pid,
            message=f"运行中 {host}:{port}",
        )

    try:
        pid_state = _pid_state(pid)
    except (OSError, SystemError, ValueError):
        pid_state = "unknown"
    if pid_state == "dead":
        remove_server_meta(config.data_dir)
        return ServerStatus(running=False, message="未运行")

    if port:
        return ServerStatus(
            running=False,
            url=url,
            port=port,
            pid=pid,
            message="进程存在但服务未就绪",
        )

    return ServerStatus(running=False, message="未运行")


def start_server(
    root: Path | None = None,
    log: LogCallback | None = None,
    progress: ProgressCallback | None = None,
) -> tuple[bool, str]:
    root = root or get_root()
    current = get_status(root)
    if current.running and current.url:
        if log:
            log(f"服务已在运行：{current.url}")
        return True, current.url

    if not is_venv_valid(root):
        ensure_venv(root, log)
    pyw = venv_pythonw(root)
    if not pyw.exists():
        return False, "未找到 pythonw，请先更新依赖。"

    log_path = _server_startup_log(root)
    _emit_progress(progress, "launch", 3, 4, "[3/4] 启动服务…", log=log)
    with open(log_path, "a", encoding="utf-8") as err_file:
        err_file.write(f"\n--- start {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        proc = subprocess.Popen(
            [str(pyw), "-m", "novel_world.web.run"],
            cwd=root,
            env=_child_env(root),
            stderr=err_file,
            creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )

    deadline = time.monotonic() + STARTUP_TIMEOUT_SEC
    while time.monotonic() < deadline:
        status = get_status(root)
        if status.running and status.url:
            if log:
                log(f"服务已就绪：{status.url}")
            _emit_progress(progress, "launch", 3, 4, f"服务已就绪：{status.url}", log=None)
            return True, status.url
        time.sleep(POLL_INTERVAL_SEC)

    _grace_deadline = time.monotonic() + 10
    while time.monotonic() < _grace_deadline:
        status = get_status(root)
        if status.running and status.url:
            if log:
                log(f"服务已就绪：{status.url}")
            _emit_progress(progress, "launch", 3, 4, f"服务已就绪：{status.url}", log=None)
            return True, status.url
        time.sleep(POLL_INTERVAL_SEC)
    return False, "启动超时，请查看 logs/server-startup.log 或控制台日志。"


def open_browser(root: Path | None = None, path: str = "") -> tuple[bool, str]:
    status = get_status(root)
    if not status.running or not status.url:
        return False, "服务未运行，请先启动。"
    base = status.url.rstrip("/")
    suffix = (path or "").strip()
    if suffix and not suffix.startswith("/"):
        suffix = "/" + suffix
    target = base + suffix if suffix else base
    webbrowser.open(target, new=2)
    return True, f"已打开 {target}"


def stop_server(root: Path | None = None, log: LogCallback | None = None) -> tuple[bool, str]:
    root = root or get_root()
    status = get_status(root)
    if not status.running or not status.port:
        if log:
            log("服务未在运行。")
        return True, "服务未在运行。"

    host = "127.0.0.1"
    meta = read_server_meta(default_config(root).data_dir) or {}
    host = str(meta.get("host") or host)
    port = status.port
    try:
        with httpx.Client(timeout=2.0) as client:
            resp = client.post(f"http://{host}:{port}/api/server/stop")
            if resp.status_code == 200 and resp.json().get("ok"):
                if log:
                    log("已发送停止请求。")
    except Exception as e:
        if log:
            log(f"API 停止请求异常（将强制清理）：{e}")

    config = default_config(root)
    remove_server_meta(config.data_dir)
    return True, "服务已停止。"


# ----------------------------------------------------------------
# Upgrade / update helpers
# ----------------------------------------------------------------

WINGET_PYTHON_IDS = ["Python.Python.3.13", "Python.Python.3.12", "Python.Python.3.11"]


def check_python_upgrade_available() -> dict[str, Any]:
    """检查是否有更新的兼容 Python 版本可用。"""
    current = find_system_python()
    if current is None:
        return {
            "upgrade_available": False,
            "current_version": "",
            "latest_compatible": "",
            "message": "未检测到 Python",
        }
    ver = _query_python_version(current)
    if ver is None:
        return {
            "upgrade_available": False,
            "current_version": "",
            "latest_compatible": "",
            "message": "无法获取 Python 版本",
        }
    current_str = f"{ver[0]}.{ver[1]}.{ver[2]}"
    for py_id in WINGET_PYTHON_IDS:
        parts = py_id.split(".")
        if len(parts) >= 3:
            try:
                major = int(parts[-2])
                minor = int(parts[-1])
                if (major, minor) > (ver[0], ver[1]) and (major, minor) >= MIN_PYTHON:
                    return {
                        "upgrade_available": True,
                        "current_version": current_str,
                        "latest_compatible": f"{major}.{minor}",
                        "message": f"可升级到 Python {major}.{minor}",
                    }
            except ValueError:
                continue
    return {
        "upgrade_available": False,
        "current_version": current_str,
        "latest_compatible": current_str,
        "message": f"Python {current_str} 已是最新兼容版本",
    }


def upgrade_python(log: LogCallback | None = None) -> tuple[bool, str]:
    """升级到最新兼容的 Python 版本。"""
    return install_python_via_winget(log)


def check_deps_upgrade_available(root: Path | None = None) -> dict[str, Any]:
    """检查 venv 中是否有可升级的依赖包。"""
    root = root or get_root()
    py = venv_python(root)
    if not py.is_file() or not is_venv_valid(root):
        return {"upgrade_available": False, "message": "虚拟环境未就绪"}

    try:
        proc = subprocess.run(
            [str(py), "-m", "pip", "list", "--outdated", "--format=json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if proc.returncode != 0:
            return {"upgrade_available": False, "message": "无法检查更新"}

        outdated = json.loads(proc.stdout)
        relevant = [
            pkg
            for pkg in outdated
            if pkg.get("name")
            in ("pywebview", "webview", "fastapi", "uvicorn", "httpx", "jinja2", "bottle", "pythonnet", "clr", "clr-loader")
        ]
        if relevant:
            names = [p["name"] for p in relevant]
            return {
                "upgrade_available": True,
                "packages": names,
                "count": len(names),
                "message": f"可升级 {len(names)} 个包：{', '.join(names[:6])}",
            }
        return {"upgrade_available": False, "message": "所有依赖已是最新"}
    except Exception as e:
        return {"upgrade_available": False, "message": str(e)}


def upgrade_launcher_deps(root: Path | None = None, log: LogCallback | None = None) -> tuple[bool, str]:
    """升级 venv 中的 launcher 依赖包。"""
    root = root or get_root()
    py = ensure_venv(root, log)
    if log:
        log("正在升级启动器依赖…")
    env = _pip_subprocess_env(root)
    proc = subprocess.run(
        [str(py), "-m", "pip", "install", "--upgrade", "-e", f"{root}[launcher]"],
        cwd=root,
        env=env,
        capture_output=True,
        timeout=300,
        creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    if log:
        text = _decode_subprocess_output(proc)
        for line in text.splitlines():
            if line.strip():
                log(line)
    if proc.returncode != 0:
        msg = "依赖升级失败"
        if log:
            log(msg)
        return False, msg
    _write_sentinel_mtime(root)
    msg = "依赖已升级到最新兼容版本"
    if log:
        log(msg)
    return True, msg
