from __future__ import annotations

import sys
import threading
from typing import Any

from novel_world.launcher import bootstrap
from novel_world.launcher import launcher_admin
from novel_world.launcher import mods_admin
from novel_world.launcher import prefs_admin
from novel_world.launcher import providers_admin
from novel_world.launcher import world_admin


def _empty_task() -> dict[str, Any]:
    return {
        "running": False,
        "kind": "",
        "phase": "",
        "step": 0,
        "total": 0,
        "percent": 0,
        "indeterminate": False,
        "label": "",
        "ok": None,
        "message": "",
        "url": "",
        "status": None,
        "logs": [],
        "prerequisites": None,
    }


class LauncherApi:
    """pywebview js_api：供前端调用的启动器接口。"""

    def __init__(self) -> None:
        self._log_lines: list[str] = []
        self._lock = threading.Lock()
        self._task: dict[str, Any] = _empty_task()

    def ping(self) -> dict[str, Any]:
        return {"ok": True}

    def get_task_status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._task)

    def _set_task(self, **fields: Any) -> None:
        with self._lock:
            self._task.update(fields)

    def _make_progress(self, kind: str, phase: str) -> Any:
        def _progress(p: str, step: int, total: int, message: str) -> None:
            percent = int(step / total * 100) if total > 0 else 0
            self._set_task(
                kind=kind,
                phase=p or phase,
                step=step,
                total=total,
                percent=min(100, max(0, percent)),
                indeterminate=False,
                label=message,
            )

        return _progress

    def _start_task(self, kind: str, label: str, *, indeterminate: bool = False) -> bool:
        with self._lock:
            if self._task.get("running"):
                return False
            self._log_lines.clear()
            self._task = _empty_task()
            self._task.update(
                {
                    "running": True,
                    "kind": kind,
                    "label": label,
                    "indeterminate": indeterminate,
                    "percent": 0 if not indeterminate else -1,
                }
            )
        return True

    def _finish_task(
        self,
        *,
        ok: bool,
        message: str,
        url: str = "",
        status: dict[str, Any] | None = None,
        prerequisites: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            self._task.update(
                {
                    "running": False,
                    "ok": ok,
                    "message": message,
                    "url": url,
                    "status": status,
                    "logs": list(self._log_lines),
                    "prerequisites": prerequisites,
                    "percent": 100 if ok else self._task.get("percent", 0),
                    "indeterminate": False,
                    "label": message,
                }
            )

    def _run_in_thread(self, kind: str, label: str, worker: Any, *, indeterminate: bool = False) -> dict[str, Any]:
        if not self._start_task(kind, label, indeterminate=indeterminate):
            return {"ok": False, "message": "已有任务进行中", "started": False}

        def _target() -> None:
            try:
                worker()
            except bootstrap.ProjectRootNotFoundError as e:
                self._append_log(str(e))
                self._finish_task(ok=False, message=str(e))
            except bootstrap.PythonNotFoundError as e:
                self._append_log(str(e))
                self._finish_task(ok=False, message=str(e))
            except Exception as e:
                self._append_log(str(e))
                self._finish_task(ok=False, message=str(e))

        threading.Thread(target=_target, daemon=True).start()
        return {"ok": True, "started": True}

    def launch_async(self, open_browser: bool = True) -> dict[str, Any]:
        def _work() -> None:
            progress = self._make_progress("launch", "launch")
            ok, message = bootstrap.launch(
                log=self._append_log,
                progress=progress,
                open_after=open_browser,
            )
            status = bootstrap.get_status().to_dict()
            self._finish_task(
                ok=ok,
                message=message,
                url=status.get("url", "") if ok else "",
                status=status,
            )

        return self._run_in_thread("launch", "[1/4] 准备启动…", _work)

    def install_environment_async(
        self,
        recreate_venv: bool = False,
        install_python: bool = False,
    ) -> dict[str, Any]:
        def _work() -> None:
            progress = self._make_progress("install", "install")
            ok, message = bootstrap.install_environment(
                log=self._append_log,
                progress=progress,
                force=True,
                recreate_venv=recreate_venv,
                install_python=install_python,
            )
            self._finish_task(
                ok=ok,
                message=message,
                prerequisites=bootstrap.check_prerequisites(),
            )

        return self._run_in_thread("install", "[1/4] 准备安装环境…", _work)

    def check_prerequisites_async(self) -> dict[str, Any]:
        def _work() -> None:
            self._set_task(label="检测运行环境…", indeterminate=True, percent=-1)
            pre = bootstrap.check_prerequisites()
            self._finish_task(
                ok=True,
                message="检测完成",
                prerequisites=pre,
            )

        return self._run_in_thread("check", "检测中…", _work, indeterminate=True)

    def _append_log(self, line: str) -> None:
        with self._lock:
            self._log_lines.append(line)
            if len(self._log_lines) > 200:
                self._log_lines = self._log_lines[-200:]

    def get_logs(self) -> list[str]:
        with self._lock:
            return list(self._log_lines)

    def clear_logs(self) -> dict[str, Any]:
        with self._lock:
            self._log_lines.clear()
        return {"ok": True}

    def get_status(self) -> dict[str, Any]:
        try:
            return bootstrap.get_status().to_dict()
        except bootstrap.ProjectRootNotFoundError as e:
            return {"running": False, "message": str(e), "url": "", "port": 0, "pid": 0}

    def get_system_info(self) -> dict[str, Any]:
        try:
            return bootstrap.get_system_info()
        except bootstrap.ProjectRootNotFoundError as e:
            return {
                "launcher_version": bootstrap.LAUNCHER_VERSION,
                "app_version": "—",
                "python_version": (
                    f"{sys.version_info.major}."
                    f"{sys.version_info.minor}."
                    f"{sys.version_info.micro}"
                ),
                "root": "",
                "root_ok": False,
                "root_error": str(e),
                "venv_exists": False,
                "deps_need_install": True,
                "status": {"running": False, "message": str(e)},
                "paths": {},
            }

    def open_directory(self, name: str) -> dict[str, Any]:
        try:
            ok, message = bootstrap.open_directory(name)
            return {"ok": ok, "message": message}
        except bootstrap.ProjectRootNotFoundError as e:
            return {"ok": False, "message": str(e)}
        except OSError as e:
            return {"ok": False, "message": str(e)}

    def get_prerequisites(self) -> dict[str, Any]:
        try:
            return bootstrap.check_prerequisites()
        except Exception as e:
            return {
                "python_ok": False,
                "python_path": "",
                "python_version": "",
                "webview2_ok": False,
                "root_ok": False,
                "root_error": str(e),
                "venv_exists": False,
                "deps_need_install": True,
                "ready": False,
            }

    def install_environment(
        self,
        recreate_venv: bool = False,
        install_python: bool = False,
    ) -> dict[str, Any]:
        try:
            ok, message = bootstrap.install_environment(
                log=self._append_log,
                force=True,
                recreate_venv=recreate_venv,
                install_python=install_python,
            )
            return {
                "ok": ok,
                "message": message,
                "logs": self.get_logs(),
                "prerequisites": bootstrap.check_prerequisites(),
            }
        except bootstrap.ProjectRootNotFoundError as e:
            self._append_log(str(e))
            return {
                "ok": False,
                "message": str(e),
                "logs": self.get_logs(),
                "prerequisites": bootstrap.check_prerequisites(),
            }
        except bootstrap.PythonNotFoundError as e:
            self._append_log(str(e))
            return {
                "ok": False,
                "message": str(e),
                "logs": self.get_logs(),
                "prerequisites": bootstrap.check_prerequisites(),
            }

    def install_deps(self, force: bool = False) -> dict[str, Any]:
        try:
            ok, message = bootstrap.install_deps(
                force=force,
                log=self._append_log,
            )
            return {"ok": ok, "message": message, "logs": self.get_logs()}
        except bootstrap.ProjectRootNotFoundError as e:
            self._append_log(str(e))
            return {"ok": False, "message": str(e), "logs": self.get_logs()}

    def launch(self, open_browser: bool = True) -> dict[str, Any]:
        try:
            ok, message = bootstrap.launch(
                log=self._append_log,
                open_after=open_browser,
            )
            status = bootstrap.get_status()
            return {
                "ok": ok,
                "message": message,
                "url": status.url if ok else "",
                "status": status.to_dict(),
                "logs": self.get_logs(),
            }
        except bootstrap.ProjectRootNotFoundError as e:
            self._append_log(str(e))
            return {
                "ok": False,
                "message": str(e),
                "logs": self.get_logs(),
                "status": {"running": False, "message": str(e)},
            }

    def start_server(self) -> dict[str, Any]:
        try:
            ok, message = bootstrap.start_server(log=self._append_log)
            status = bootstrap.get_status()
            return {
                "ok": ok,
                "message": message,
                "url": status.url if ok else "",
                "status": status.to_dict(),
                "logs": self.get_logs(),
            }
        except bootstrap.ProjectRootNotFoundError as e:
            self._append_log(str(e))
            return {"ok": False, "message": str(e), "logs": self.get_logs()}

    def open_browser(self, path: str = "") -> dict[str, Any]:
        try:
            ok, message = bootstrap.open_browser(path=path)
            return {"ok": ok, "message": message}
        except bootstrap.ProjectRootNotFoundError as e:
            return {"ok": False, "message": str(e)}

    def stop_server(self) -> dict[str, Any]:
        try:
            ok, message = bootstrap.stop_server(log=self._append_log)
            return {
                "ok": ok,
                "message": message,
                "status": bootstrap.get_status().to_dict(),
                "logs": self.get_logs(),
            }
        except bootstrap.ProjectRootNotFoundError as e:
            return {"ok": False, "message": str(e), "status": {"running": False}}

    # --- 世界管理（直连本地数据库，无需启动 Web 服务）---

    def list_worlds(self) -> dict[str, Any]:
        try:
            return world_admin.list_worlds()
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def get_world(self, world_id: str) -> dict[str, Any]:
        try:
            return world_admin.get_world(world_id)
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def create_world(
        self,
        name: str,
        description: str = "",
        genre: str = "",
        rules_json: str = "{}",
        settings_json: str = "{}",
    ) -> dict[str, Any]:
        try:
            return world_admin.create_world(name, description, genre, rules_json, settings_json)
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def update_world(
        self,
        world_id: str,
        name: str,
        description: str = "",
        genre: str = "",
        rules_json: str = "{}",
        settings_json: str = "{}",
    ) -> dict[str, Any]:
        try:
            return world_admin.update_world(
                world_id, name, description, genre, rules_json, settings_json
            )
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def delete_world(self, world_id: str) -> dict[str, Any]:
        try:
            return world_admin.delete_world(world_id)
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def update_world_user_persona(
        self,
        world_id: str,
        persona_name: str = "",
        persona_description: str = "",
    ) -> dict[str, Any]:
        try:
            return world_admin.update_world_user_persona(
                world_id, persona_name, persona_description
            )
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def upload_world_background(
        self, world_id: str, filename: str, data_b64: str
    ) -> dict[str, Any]:
        try:
            return world_admin.upload_world_background(world_id, filename, data_b64)
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def clear_world_background(self, world_id: str) -> dict[str, Any]:
        try:
            return world_admin.clear_world_background(world_id)
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def import_world_pack(self, filename: str, data_b64: str) -> dict[str, Any]:
        try:
            return world_admin.import_world_pack(filename, data_b64)
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def export_world_pack(self, world_id: str, include_uploads: bool = True) -> dict[str, Any]:
        try:
            return world_admin.export_world_pack(world_id, include_uploads)
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def create_character(self, world_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return world_admin.create_character(world_id, payload or {})
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def update_character(
        self, world_id: str, character_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            return world_admin.update_character(world_id, character_id, payload or {})
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def delete_character(self, world_id: str, character_id: str) -> dict[str, Any]:
        try:
            return world_admin.delete_character(world_id, character_id)
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def upload_character_avatar(
        self, world_id: str, character_id: str, filename: str, data_b64: str
    ) -> dict[str, Any]:
        try:
            return world_admin.upload_character_avatar(
                world_id, character_id, filename, data_b64
            )
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def import_character_card(
        self, world_id: str, character_id: str, filename: str, data_b64: str
    ) -> dict[str, Any]:
        try:
            return world_admin.import_character_card(
                world_id, character_id, filename, data_b64
            )
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def export_character_card(
        self, world_id: str, character_id: str, fmt: str = "json"
    ) -> dict[str, Any]:
        try:
            return world_admin.export_character_card(world_id, character_id, fmt)
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def set_state(
        self,
        world_id: str,
        key: str,
        value_json: str = "",
        scope: str = "world",
        scope_id: str = "",
    ) -> dict[str, Any]:
        try:
            return world_admin.set_state(world_id, key, value_json, scope, scope_id)
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def upload_world_document(
        self, world_id: str, filename: str, data_b64: str
    ) -> dict[str, Any]:
        try:
            return world_admin.upload_world_document(world_id, filename, data_b64)
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def delete_world_document(self, world_id: str, doc_id: str) -> dict[str, Any]:
        try:
            return world_admin.delete_world_document(world_id, doc_id)
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def create_lore_entry(self, world_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return world_admin.create_lore_entry(world_id, payload or {})
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def update_lore_entry(
        self, world_id: str, entry_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            return world_admin.update_lore_entry(world_id, entry_id, payload or {})
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def delete_lore_entry(self, world_id: str, entry_id: str) -> dict[str, Any]:
        try:
            return world_admin.delete_lore_entry(world_id, entry_id)
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def import_st_world_info(
        self,
        world_id: str,
        filename: str,
        data_b64: str,
        scope: str = "world",
        character_id: str = "",
        mode: str = "merge",
    ) -> dict[str, Any]:
        try:
            return world_admin.import_st_world_info(
                world_id, filename, data_b64, scope, character_id, mode
            )
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def export_st_world_info(
        self, world_id: str, scope: str = "", character_id: str = ""
    ) -> dict[str, Any]:
        try:
            return world_admin.export_st_world_info(world_id, scope, character_id)
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def import_st_preset(self, filename: str, data_b64: str) -> dict[str, Any]:
        try:
            return prefs_admin.import_st_preset(filename, data_b64)
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def import_st_regex(self, filename: str, data_b64: str) -> dict[str, Any]:
        try:
            return prefs_admin.import_st_regex(filename, data_b64)
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def import_st_stscript(self, filename: str, data_b64: str) -> dict[str, Any]:
        try:
            return prefs_admin.import_st_stscript(filename, data_b64)
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def create_save(
        self, world_id: str, slot_index: int, label: str = ""
    ) -> dict[str, Any]:
        try:
            return world_admin.create_save(world_id, slot_index, label)
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def load_save(self, world_id: str, save_id: str) -> dict[str, Any]:
        try:
            return world_admin.load_save(world_id, save_id)
        except Exception as e:
            return {"ok": False, "message": str(e)}

    # --- API 提供商管理（直连本地数据库，无需启动 Web 服务）---

    def list_providers(self) -> dict[str, Any]:
        try:
            return providers_admin.list_providers()
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def list_vendor_catalog(self) -> dict[str, Any]:
        try:
            return providers_admin.list_vendor_catalog()
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def create_provider(
        self,
        name: str = "",
        provider_type: str = "",
        api_key: str = "",
        base_url: str = "",
        model: str = "",
        preset_slug: str = "",
    ) -> dict[str, Any]:
        try:
            return providers_admin.create_provider(
                name, provider_type, api_key, base_url, model, preset_slug
            )
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def delete_provider(self, provider_id: str) -> dict[str, Any]:
        try:
            return providers_admin.delete_provider(provider_id)
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def test_provider(self, provider_id: str, model: str = "") -> dict[str, Any]:
        try:
            return providers_admin.test_provider(provider_id, model)
        except Exception as e:
            return {"ok": False, "message": str(e)}

    # --- MOD 管理（直连本地数据库，无需启动 Web 服务）---

    def list_mods(self, reload: bool = False) -> dict[str, Any]:
        try:
            return mods_admin.list_mods(reload=reload)
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def set_mod_enabled(self, mod_id: str, enabled: bool = True) -> dict[str, Any]:
        try:
            return mods_admin.set_mod_enabled(mod_id, enabled)
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def open_mods_directory(self) -> dict[str, Any]:
        try:
            return mods_admin.open_mods_directory()
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def install_mod_zip(self, filename: str, data_b64: str) -> dict[str, Any]:
        try:
            return mods_admin.install_mod_zip_file(filename, data_b64)
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def uninstall_mod(self, mod_id: str) -> dict[str, Any]:
        try:
            return mods_admin.uninstall_mod_by_id(mod_id)
        except Exception as e:
            return {"ok": False, "message": str(e)}

    # --- 启动器外观 ---

    def get_launcher_appearance(self) -> dict[str, Any]:
        try:
            return launcher_admin.get_launcher_appearance()
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def upload_launcher_background(self, filename: str, data_b64: str) -> dict[str, Any]:
        try:
            return launcher_admin.upload_launcher_background(filename, data_b64)
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def clear_launcher_background(self) -> dict[str, Any]:
        try:
            return launcher_admin.clear_launcher_background()
        except Exception as e:
            return {"ok": False, "message": str(e)}


    # --- 更新检查 ---

    def check_updates(self) -> dict[str, Any]:
        """同步检测可用的 Python 和依赖更新。"""
        result: dict[str, Any] = {"python": None, "deps": None}
        try:
            result["python"] = bootstrap.check_python_upgrade_available()
        except Exception as e:
            result["python"] = {"upgrade_available": False, "message": str(e)}
        try:
            result["deps"] = bootstrap.check_deps_upgrade_available()
        except Exception as e:
            result["deps"] = {"upgrade_available": False, "message": str(e)}
        result["any_available"] = bool(
            result["python"].get("upgrade_available")
            or result["deps"].get("upgrade_available")
        )
        return result

    def check_updates_async(self) -> dict[str, Any]:
        """异步检测可用更新。"""
        def _work() -> None:
            self._set_task(label="检查更新中…", indeterminate=True, percent=-1)
            result = self.check_updates()
            self._finish_task(
                ok=True,
                message="检查完成",
                prerequisites={"updates": result},
            )
        return self._run_in_thread("check", "检查更新…", _work, indeterminate=True)

    def upgrade_python_async(self) -> dict[str, Any]:
        """异步升级 Python 到最新兼容版本。"""
        def _work() -> None:
            progress = self._make_progress("upgrade", "python")
            ok, message = bootstrap.upgrade_python(log=self._append_log)
            self._finish_task(ok=ok, message=message, prerequisites=bootstrap.check_prerequisites())
        return self._run_in_thread("upgrade", "正在升级 Python…", _work)

    def upgrade_deps_async(self) -> dict[str, Any]:
        """异步升级依赖包。"""
        def _work() -> None:
            progress = self._make_progress("upgrade", "deps")
            ok, message = bootstrap.upgrade_launcher_deps(log=self._append_log)
            self._finish_task(ok=ok, message=message, prerequisites=bootstrap.check_prerequisites())
        return self._run_in_thread("upgrade", "正在升级依赖…", _work)

    def upgrade_all_async(self) -> dict[str, Any]:
        """异步一键升级 Python + 依赖。"""
        def _work() -> None:
            progress = self._make_progress("upgrade", "all")
            # Step 1: Python
            self._set_task(label="[1/2] 升级 Python…", indeterminate=True, percent=-1)
            py_ok, py_msg = bootstrap.upgrade_python(log=self._append_log)
            self._append_log(py_msg)
            # Step 2: Deps
            self._set_task(label="[2/2] 升级依赖…", indeterminate=True, percent=-1)
            dep_ok, dep_msg = bootstrap.upgrade_launcher_deps(log=self._append_log)
            self._append_log(dep_msg)
            msg = "; ".join(filter(None, [py_msg, dep_msg]))
            self._finish_task(
                ok=py_ok or dep_ok,
                message=msg,
                prerequisites=bootstrap.check_prerequisites(),
            )
        return self._run_in_thread("upgrade", "一键升级中…", _work)

    def get_available_pythons(self) -> list[dict[str, str]]:
        """返回系统上所有兼容 Python 版本列表，标记当前使用的版本。"""
        all_pythons = bootstrap.find_all_compatible_pythons()
        try:
            root = bootstrap.get_root()
            venv_py = bootstrap.venv_python(root)
            if venv_py.is_file():
                venv_path = str(venv_py.resolve())
                for p in all_pythons:
                    if p["path"].lower() == venv_path.lower():
                        p["active"] = "true"
                        break
                else:
                    # Venv exists but Python not in list — add it
                    ver = bootstrap._query_python_version(venv_py)
                    if ver:
                        all_pythons.insert(0, {
                            "path": str(venv_py.resolve()),
                            "version": f"{ver[0]}.{ver[1]}.{ver[2]}",
                            "major_minor": f"{ver[0]}.{ver[1]}",
                            "active": "true",
                        })
        except Exception:
            pass
        for p in all_pythons:
            p.setdefault("active", "false")
        return all_pythons

    def switch_python_async(self, python_path: str) -> dict[str, Any]:
        """异步切换到指定 Python 版本（重建 venv + 重装依赖）。"""
        def _work() -> None:
            progress = self._make_progress("switch", "python")
            ok, message = bootstrap.switch_python(
                python_path, log=self._append_log
            )
            self._finish_task(
                ok=ok,
                message=message,
                prerequisites=bootstrap.check_prerequisites(),
            )
        return self._run_in_thread("switch", "正在切换 Python 版本…", _work)

    def save_launcher_appearance(
        self, overlay: float = 0.55, blur: int = 8, fit: str = "cover"
    ) -> dict[str, Any]:
        try:
            return launcher_admin.save_launcher_appearance(overlay, blur, fit)
        except Exception as e:
            return {"ok": False, "message": str(e)}
