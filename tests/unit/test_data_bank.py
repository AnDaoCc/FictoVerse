import sqlite3

from novel_world.modules.world.services.data_bank_service import DataBankService


def test_data_bank_index_and_search() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE data_bank_chunks (
            id TEXT PRIMARY KEY, scope TEXT, world_id TEXT, session_ref TEXT, document_id TEXT,
            title TEXT, chunk_index INTEGER, content TEXT, embedding_json TEXT, enabled INTEGER,
            created_at TEXT, updated_at TEXT
        );
        """
    )
    svc = DataBankService(conn)
    svc.index_text(world_id="w1", title="设定", content="龙之谷位于北方雪山。")
    hits = svc.search("w1", "龙", top_k=3, min_score=0.0)
    assert hits
