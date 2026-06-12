from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from novel_world.launcher import deps_install


def test_pick_wheel_prefers_py3_none_any() -> None:
    urls = [
        {"packagetype": "bdist_wheel", "filename": "pkg-1.0-py3-none-any.whl", "url": "http://x"},
        {"packagetype": "sdist", "filename": "pkg-1.0.tar.gz", "url": "http://y"},
    ]
    picked = deps_install.pick_wheel(urls, py_major=3, py_minor=11, platform="win32")
    assert picked is not None
    assert picked["filename"] == "pkg-1.0-py3-none-any.whl"


def test_wheels_dir_under_project_root(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    assert deps_install.wheels_dir(root) == root / "packaging" / "wheels" / "launcher"


@patch("novel_world.launcher.deps_install._fetch_json_no_proxy")
@patch("novel_world.launcher.deps_install._download_no_proxy")
def test_download_wheels_no_proxy(mock_download, mock_fetch, tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()

    def fake_fetch(url: str) -> dict:
        return {
            "urls": [
                {
                    "packagetype": "bdist_wheel",
                    "filename": "pywebview-5.1-py3-none-any.whl",
                    "url": "https://example.com/pywebview.whl",
                }
            ]
        }

    mock_fetch.side_effect = fake_fetch
    saved = deps_install.download_wheels_no_proxy(root)
    assert len(saved) == len(deps_install.DOWNLOAD_PACKAGES)
    assert mock_download.called


def test_install_launcher_deps_offline_uses_vendor_proxy_tools(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "proj"
    wheels = root / "packaging" / "wheels" / "launcher"
    wheels.mkdir(parents=True)
    (wheels / "pywebview-5.1-py3-none-any.whl").write_bytes(b"whl")
    (wheels / "bottle-0.1-py3-none-any.whl").write_bytes(b"whl")
    (wheels / "typing_extensions-4.0-py3-none-any.whl").write_bytes(b"whl")
    (wheels / "pythonnet-3.0-py3-none-any.whl").write_bytes(b"whl")
    vendor = wheels / "proxy_tools-0.1.0"
    vendor.mkdir()
    (vendor / "setup.py").write_text("from setuptools import setup\nsetup(name='proxy_tools')\n", encoding="utf-8")

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return MagicMock(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(deps_install.subprocess, "run", fake_run)
    py = root / "python.exe"
    py.write_text("", encoding="utf-8")
    ok = deps_install.install_launcher_deps_offline(py, root)
    assert ok is True
    assert any("proxy_tools" in " ".join(cmd) for cmd in calls)
    assert any(cmd[-1].endswith(".whl") for cmd in calls)
