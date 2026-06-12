from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from novel_world.launcher.bootstrap import LogCallback

MIRROR_JSON = "https://pypi.tuna.tsinghua.edu.cn/pypi/{package}/json"
FALLBACK_JSON = "https://pypi.org/pypi/{package}/json"
DOWNLOAD_PACKAGES = ("pywebview", "bottle", "typing-extensions", "pythonnet", "setuptools", "wheel", "clr_loader")


def wheels_dir(root: Path) -> Path:
    return root / "packaging" / "wheels" / "launcher"


def proxy_tools_vendor_dir(root: Path) -> Path:
    return wheels_dir(root) / "proxy_tools-0.1.0"


def _fetch_json_no_proxy(url: str) -> dict:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url, timeout=60) as resp:
        return json.load(resp)


def _download_no_proxy(url: str, dest: Path) -> None:
    if dest.is_file() and dest.stat().st_size > 0:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url, timeout=120) as resp, dest.open("wb") as out:
        out.write(resp.read())


def pick_wheel(urls: list[dict], *, py_major: int, py_minor: int, platform: str) -> dict | None:
    py_tag = f"cp{py_major}{py_minor}"
    candidates = [u for u in urls if u.get("packagetype") == "bdist_wheel"]
    if not candidates:
        return None
    if platform == "win32":
        for item in candidates:
            name = item.get("filename", "")
            if "win_amd64" in name and py_tag in name:
                return item
    for item in candidates:
        if str(item.get("filename", "")).endswith("py3-none-any.whl"):
            return item
    return candidates[0]


def download_wheels_no_proxy(root: Path, log: LogCallback | None = None) -> list[Path]:
    saved: list[Path] = []
    target = wheels_dir(root)
    target.mkdir(parents=True, exist_ok=True)
    for package in DOWNLOAD_PACKAGES:
        meta: dict | None = None
        for template in (MIRROR_JSON, FALLBACK_JSON):
            try:
                meta = _fetch_json_no_proxy(template.format(package=package))
                break
            except Exception:
                continue
        if meta is None:
            if log:
                log(f"[offline] 无法获取 {package} 元数据")
            continue
        wheel = pick_wheel(
            meta.get("urls") or [],
            py_major=sys.version_info.major,
            py_minor=sys.version_info.minor,
            platform=sys.platform,
        )
        if wheel is None:
            if log:
                log(f"[offline] {package} 无可用 wheel")
            continue
        filename = str(wheel["filename"])
        dest = target / filename
        try:
            _download_no_proxy(str(wheel["url"]), dest)
            saved.append(dest)
            if log:
                log(f"[offline] 已缓存 {filename}")
        except Exception as exc:
            if log:
                log(f"[offline] 下载 {filename} 失败: {exc}")
    return saved


def install_proxy_tools_from_vendor(
    py: Path,
    root: Path,
    *,
    env: dict[str, str] | None = None,
    log: LogCallback | None = None,
) -> bool:
    vendor = proxy_tools_vendor_dir(root)
    if not (vendor / "setup.py").is_file():
        tar = wheels_dir(root) / "proxy_tools-0.1.0.tar.gz"
        if tar.is_file():
            import tarfile

            with tarfile.open(tar, "r:gz") as archive:
                archive.extractall(wheels_dir(root))
        else:
            if log:
                log("[offline] 缺少 proxy_tools 离线包")
            return False
    proc = subprocess.run(
        [
            str(py),
            "-m",
            "pip",
            "install",
            "--no-build-isolation",
            str(vendor),
        ],
        cwd=root,
        env=env,
        capture_output=True,
    )
    if log:
        _log_subprocess(proc, log)
    return proc.returncode == 0


def install_launcher_deps_offline(
    py: Path,
    root: Path,
    *,
    env: dict[str, str] | None = None,
    log: LogCallback | None = None,
) -> bool:
    target = wheels_dir(root)
    if not any(target.glob("*.whl")):
        download_wheels_no_proxy(root, log=log)
    if not install_proxy_tools_from_vendor(py, root, env=env, log=log):
        return False
    required_patterns = (
        "typing_extensions-*.whl",
        "bottle-*.whl",
        "pythonnet-*.whl",
        "pywebview-*.whl",
    )
    optional_patterns = (
        "setuptools-*.whl",
        "wheel-*.whl",
        "clr_loader-*.whl",
    )
    for pattern in (*required_patterns, *optional_patterns):
        matched = sorted(target.glob(pattern))
        if not matched:
            if pattern in required_patterns:
                if log:
                    log(f"[offline] 缺少 wheel：{pattern}")
                return False
            continue
        proc = subprocess.run(
            [str(py), "-m", "pip", "install", "--no-deps", str(matched[-1])],
            cwd=root,
            env=env,
            capture_output=True,
        )
        if log:
            _log_subprocess(proc, log)
        if proc.returncode != 0:
            return False
    verify = subprocess.run([str(py), "-c", "import webview; import proxy_tools"], cwd=root, env=env)
    return verify.returncode == 0


def install_environment_offline_fallback(
    py: Path,
    root: Path,
    *,
    env: dict[str, str] | None = None,
    log: LogCallback | None = None,
    pip_run: Callable[..., tuple[bool, str]] | None = None,
) -> tuple[bool, str]:
    if log:
        log("在线安装失败，尝试离线 wheel…")
    if not install_launcher_deps_offline(py, root, env=env, log=log):
        return False, "离线 launcher 依赖安装失败"
    if pip_run is None:
        return False, "pip 执行器未配置"
    ok, message = pip_run(
        py,
        root,
        ["install", "-e", ".[dev,launcher]", "--upgrade", "--no-build-isolation"],
        log,
    )
    if ok:
        return True, message
    return False, message or "离线 editable 安装失败"


def _log_subprocess(proc: subprocess.CompletedProcess[bytes], log: LogCallback) -> None:
    from novel_world.launcher.bootstrap import _decode_subprocess_output

    text = _decode_subprocess_output(proc)
    for line in text.splitlines():
        if line.strip():
            log(line)
