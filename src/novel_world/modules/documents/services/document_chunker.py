from __future__ import annotations


def chunk_text(text: str, *, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        return []
    if len(raw) <= chunk_size:
        return [raw]
    chunks: list[str] = []
    start = 0
    while start < len(raw):
        end = min(len(raw), start + chunk_size)
        piece = raw[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(raw):
            break
        start = max(0, end - overlap)
    return chunks
