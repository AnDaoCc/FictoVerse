from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from novel_world.bootstrap.app_factory import AppFactory
from novel_world.bootstrap.config import AppConfig
from novel_world.core.domain.ids import WorldId, new_world_id
from novel_world.core.exceptions import ValidationError

PACK_SCHEMA_VERSION = 1


class WorldPackService:
    def __init__(self, config: AppConfig, app_factory: AppFactory | None = None) -> None:
        self._config = config
        self._app = app_factory or AppFactory(config)

    def export_world(self, world_id: str, *, include_uploads: bool = True) -> bytes:
        db_path = self._config.world_db_path(world_id)
        if not db_path.is_file():
            raise ValidationError(f"世界不存在: {world_id}")

        rt = self._app.open_world(WorldId(world_id))
        try:
            world = rt.world.get(WorldId(world_id))
            manifest = {
                "schema_version": PACK_SCHEMA_VERSION,
                "world_id": str(world.id),
                "name": world.name,
                "genre": world.genre,
                "include_uploads": include_uploads,
            }
        finally:
            rt.close()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            shutil.copy2(db_path, root / "world.db")
            if include_uploads:
                uploads_src = self._config.uploads_dir / "worlds" / world_id
                if uploads_src.is_dir():
                    shutil.copytree(uploads_src, root / "uploads", dirs_exist_ok=True)

            buf = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
            buf.close()
            try:
                with zipfile.ZipFile(buf.name, "w", zipfile.ZIP_DEFLATED) as zf:
                    for file in root.rglob("*"):
                        if file.is_file():
                            zf.write(file, file.relative_to(root).as_posix())
                return Path(buf.name).read_bytes()
            finally:
                Path(buf.name).unlink(missing_ok=True)

    def import_world(self, pack_bytes: bytes, *, new_world_id: str | None = None) -> dict[str, Any]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pack_path = root / "pack.zip"
            pack_path.write_bytes(pack_bytes)
            with zipfile.ZipFile(pack_path, "r") as zf:
                zf.extractall(root / "extract")

            extract = root / "extract"
            manifest_path = extract / "manifest.json"
            db_src = extract / "world.db"
            if not manifest_path.is_file() or not db_src.is_file():
                raise ValidationError("无效的世界包：缺少 manifest 或 world.db")

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if int(manifest.get("schema_version", 0)) != PACK_SCHEMA_VERSION:
                raise ValidationError("不支持的世界包版本。")

            target_id = str(new_world_id or manifest.get("world_id") or new_world_id())
            dest_db = self._config.world_db_path(target_id)
            if dest_db.exists():
                raise ValidationError(f"世界已存在，请先删除或更换包: {target_id}")
            dest_db.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(db_src, dest_db)

            uploads_src = extract / "uploads"
            if uploads_src.is_dir():
                uploads_dest = self._config.uploads_dir / "worlds" / target_id
                if uploads_dest.exists():
                    shutil.rmtree(uploads_dest)
                shutil.copytree(uploads_src, uploads_dest)

            return {"world_id": target_id, "name": manifest.get("name", ""), "manifest": manifest}
