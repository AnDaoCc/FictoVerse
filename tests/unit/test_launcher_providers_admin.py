from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from novel_world.launcher import providers_admin


def _setup_root(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
    (root / "data").mkdir()
    monkeypatch.setattr(providers_admin, "get_root", lambda: root)
    return root


def test_providers_admin_crud(tmp_path: Path, monkeypatch) -> None:
    _setup_root(tmp_path, monkeypatch)

    catalog = providers_admin.list_vendor_catalog()
    assert catalog["ok"] is True
    assert len(catalog["data"]) > 0
    preset = catalog["data"][0]

    created = providers_admin.create_provider(
        preset_slug=preset["slug"],
        api_key="sk-test-key",
    )
    assert created["ok"] is True
    provider_id = created["data"]["id"]
    assert created["data"]["api_key_masked"]

    listed = providers_admin.list_providers()
    assert listed["ok"] is True
    assert any(p["id"] == provider_id for p in listed["data"])

    with patch.object(providers_admin, "_app_ctx") as mock_app_ctx:
        mock_runtime = mock_app_ctx.return_value.open.return_value
        mock_runtime.providers.test_connection.return_value = "连接成功"
        result = providers_admin.test_provider(provider_id)
        assert result["ok"] is True
        assert "连接成功" in result["message"]

    deleted = providers_admin.delete_provider(provider_id)
    assert deleted["ok"] is True

    listed2 = providers_admin.list_providers()
    assert listed2["ok"] is True
    assert not any(p["id"] == provider_id for p in listed2["data"])


def test_providers_admin_validation(tmp_path: Path, monkeypatch) -> None:
    _setup_root(tmp_path, monkeypatch)

    bad = providers_admin.create_provider(name="", provider_type="")
    assert bad["ok"] is False
    assert "厂商" in bad["message"] or "名称" in bad["message"]
