"""
rag_indexer_lib.py — shared utilities for rag-indexer and rag-query
"""

import json
import struct
import sqlite3
from pathlib import Path

DEFAULT_CONFIG_PATH = Path.home() / ".openclaw" / "workspace" / "r-rag" / "config.json"

DEFAULT_CONFIG = {
    "ollamaUrl": "http://localhost:11434",
    "embeddingModel": "nomic-embed-text",
    "ssotRoot": str(Path.home() / ".openclaw" / "workspace" / "resonantos-alpha" / "ssot"),
    "dbPath": str(Path.home() / ".openclaw" / "workspace" / "r-rag" / "rag.db"),
    "chunkSize": 500,
    "chunkOverlap": 50,
    "topK": 5,
    "minScore": 0.65,
}

def load_config(config_path=None):
    path = Path(config_path or DEFAULT_CONFIG_PATH)
    if path.exists():
        with open(path) as f:
            user_config = json.load(f)
        return {**DEFAULT_CONFIG, **user_config}
    return DEFAULT_CONFIG.copy()

SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_path TEXT NOT NULL,
    doc_layer TEXT,
    chunk_index INTEGER,
    chunk_text TEXT NOT NULL,
    embedding BLOB NOT NULL,
    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS index_meta (
    source_path TEXT PRIMARY KEY,
    file_mtime REAL,
    chunk_count INTEGER,
    file_hash TEXT,
    indexed_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source_path);
CREATE INDEX IF NOT EXISTS idx_chunks_layer ON chunks(doc_layer);
"""

def get_db(db_path):
    path = Path(db_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript(SCHEMA)
    conn.commit()
    return conn

def serialize_embedding(embedding):
    return struct.pack(f"{len(embedding)}f", *embedding)

def deserialize_embedding(blob):
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))
