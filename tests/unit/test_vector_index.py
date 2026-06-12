import sqlite3

from novel_world.modules.ai.ports.embedding_provider import HashEmbeddingProvider
from novel_world.modules.ai.services.vector_index import VectorIndex


def test_vector_index_upsert_and_search(tmp_path) -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE vector_chunks (
            id TEXT PRIMARY KEY, scope TEXT, scope_id TEXT, source_type TEXT, source_id TEXT,
            chunk_index INTEGER, content TEXT, embedding_json TEXT, metadata_json TEXT, created_at TEXT
        );
        """
    )
    index = VectorIndex(conn, HashEmbeddingProvider(64))
    index.upsert_chunks(
        scope="test",
        scope_id="w1",
        source_type="doc",
        source_id="d1",
        chunks=["dragon lore", "castle history"],
    )
    hits = index.search("dragon", scope="test", scope_id="w1", top_k=2)
    assert hits
    assert "dragon" in hits[0][0].content.lower()
