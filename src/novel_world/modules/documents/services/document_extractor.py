from __future__ import annotations

from pathlib import Path

from docx import Document

from novel_world.core.exceptions import ValidationError


def extract_text_from_bytes(filename: str, data: bytes) -> str:
    lower = filename.lower()
    if lower.endswith(".txt"):
        for encoding in ("utf-8", "utf-8-sig", "gbk", "latin-1"):
            try:
                return data.decode(encoding).strip()
            except UnicodeDecodeError:
                continue
        raise ValidationError("无法解析文本文件编码。")
    if lower.endswith(".docx"):
        return _extract_docx(data)
    raise ValidationError("仅支持 .txt 和 .docx 文档。")


def extract_text_from_path(path: Path) -> str:
    return extract_text_from_bytes(path.name, path.read_bytes())


def _extract_docx(data: bytes) -> str:
    from io import BytesIO

    doc = Document(BytesIO(data))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs).strip()
