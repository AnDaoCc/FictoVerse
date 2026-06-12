from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from novel_world.bootstrap.config import AppConfig
from novel_world.core.domain.timestamps import utc_now
from novel_world.core.exceptions import ValidationError
from novel_world.modules.documents.services.document_extractor import extract_text_from_bytes


def _new_id() -> str:
    return str(uuid.uuid4())


@dataclass
class WorldDocument:
    id: str
    world_id: str
    filename: str
    mime_type: str
    storage_path: str
    extracted_text: str
    uploaded_at: datetime | None = None


@dataclass
class ChatAttachment:
    id: str
    session_id: str
    message_id: str | None
    filename: str
    mime_type: str
    storage_path: str
    extracted_text: str
    uploaded_at: datetime | None = None


class DocumentService:
    def __init__(self, config: AppConfig, conn) -> None:
        self._config = config
        self._conn = conn

    def list_world_documents(self, world_id: str) -> list[WorldDocument]:
        rows = self._conn.execute(
            "SELECT * FROM world_documents WHERE world_id = ? ORDER BY uploaded_at DESC",
            (world_id,),
        ).fetchall()
        return [_row_world_doc(r) for r in rows]

    def upload_world_document(self, world_id: str, filename: str, data: bytes, mime_type: str = "") -> WorldDocument:
        if not filename.strip():
            raise ValidationError("文件名不能为空。")
        lower = filename.lower()
        if not (lower.endswith(".txt") or lower.endswith(".docx")):
            raise ValidationError("世界观文档仅支持 .txt 和 .docx。")
        extracted = extract_text_from_bytes(filename, data)
        doc_id = _new_id()
        dest_dir = self._config.world_documents_dir(world_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        safe_name = f"{doc_id}_{Path(filename).name}"
        dest_path = dest_dir / safe_name
        dest_path.write_bytes(data)
        now = utc_now()
        self._conn.execute(
            """
            INSERT INTO world_documents
            (id, world_id, filename, mime_type, storage_path, extracted_text, uploaded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (doc_id, world_id, filename, mime_type, str(dest_path), extracted, now.isoformat()),
        )
        return WorldDocument(
            id=doc_id,
            world_id=world_id,
            filename=filename,
            mime_type=mime_type,
            storage_path=str(dest_path),
            extracted_text=extracted,
            uploaded_at=now,
        )

    def delete_world_document(self, doc_id: str) -> None:
        row = self._conn.execute("SELECT * FROM world_documents WHERE id = ?", (doc_id,)).fetchone()
        if row is None:
            raise ValidationError("文档不存在。")
        path = Path(row["storage_path"])
        if path.exists():
            path.unlink()
        self._conn.execute("DELETE FROM world_documents WHERE id = ?", (doc_id,))

    def list_session_attachments(self, session_id: str, *, message_id: str | None = None) -> list[ChatAttachment]:
        if message_id is None:
            rows = self._conn.execute(
                "SELECT * FROM chat_attachments WHERE session_id = ? AND message_id IS NULL ORDER BY uploaded_at",
                (session_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM chat_attachments WHERE session_id = ? AND message_id = ? ORDER BY uploaded_at",
                (session_id, message_id),
            ).fetchall()
        return [_row_attachment(r) for r in rows]

    def list_all_session_attachments(self, session_id: str) -> list[ChatAttachment]:
        rows = self._conn.execute(
            "SELECT * FROM chat_attachments WHERE session_id = ? ORDER BY uploaded_at",
            (session_id,),
        ).fetchall()
        return [_row_attachment(r) for r in rows]

    def upload_chat_attachment(
        self,
        session_id: str,
        filename: str,
        data: bytes,
        *,
        mime_type: str = "",
        message_id: str | None = None,
    ) -> ChatAttachment:
        if not filename.strip():
            raise ValidationError("文件名不能为空。")
        lower = filename.lower()
        extracted = ""
        if lower.endswith((".txt", ".docx")):
            extracted = extract_text_from_bytes(filename, data)
        elif not lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
            raise ValidationError("聊天附件仅支持 txt、docx 或常见图片格式。")

        att_id = _new_id()
        dest_dir = self._config.chat_session_uploads_dir(session_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        safe_name = f"{att_id}_{Path(filename).name}"
        dest_path = dest_dir / safe_name
        dest_path.write_bytes(data)
        now = utc_now()
        self._conn.execute(
            """
            INSERT INTO chat_attachments
            (id, session_id, message_id, filename, mime_type, storage_path, extracted_text, uploaded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                att_id,
                session_id,
                message_id,
                filename,
                mime_type,
                str(dest_path),
                extracted,
                now.isoformat(),
            ),
        )
        return ChatAttachment(
            id=att_id,
            session_id=session_id,
            message_id=message_id,
            filename=filename,
            mime_type=mime_type,
            storage_path=str(dest_path),
            extracted_text=extracted,
            uploaded_at=now,
        )

    def bind_attachments_to_message(self, attachment_ids: list[str], message_id: str) -> None:
        for att_id in attachment_ids:
            self._conn.execute(
                "UPDATE chat_attachments SET message_id = ? WHERE id = ?",
                (message_id, att_id),
            )

    def delete_chat_attachment(self, att_id: str) -> None:
        row = self._conn.execute("SELECT * FROM chat_attachments WHERE id = ?", (att_id,)).fetchone()
        if row is None:
            raise ValidationError("附件不存在。")
        path = Path(row["storage_path"])
        if path.exists():
            path.unlink()
        self._conn.execute("DELETE FROM chat_attachments WHERE id = ?", (att_id,))


def _row_world_doc(row) -> WorldDocument:
    from novel_world.core.domain.timestamps import from_iso

    return WorldDocument(
        id=row["id"],
        world_id=row["world_id"],
        filename=row["filename"],
        mime_type=row["mime_type"],
        storage_path=row["storage_path"],
        extracted_text=row["extracted_text"],
        uploaded_at=from_iso(row["uploaded_at"]),
    )


def _row_attachment(row) -> ChatAttachment:
    from novel_world.core.domain.timestamps import from_iso

    return ChatAttachment(
        id=row["id"],
        session_id=row["session_id"],
        message_id=row["message_id"],
        filename=row["filename"],
        mime_type=row["mime_type"],
        storage_path=row["storage_path"],
        extracted_text=row["extracted_text"],
        uploaded_at=from_iso(row["uploaded_at"]),
    )
