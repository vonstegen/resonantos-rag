#!/usr/bin/env python3
"""
rag-indexer.py — ResonantOS RAG Layer 4
Indexes SSoT documents into a SQLite vector store using Ollama embeddings.

Usage:
    python rag-indexer.py              # incremental (only changed files)
    python rag-indexer.py --full       # full re-index
    python rag-indexer.py --stats      # show index stats
    python rag-indexer.py --path /custom/ssot/path
"""

import os
import sys
import json
import sqlite3
import struct
import hashlib
import argparse
import time
from pathlib import Path
from datetime import datetime

try:
    import requests
except ImportError:
    print("ERROR: 'requests' not installed. Run: pip install requests")
    sys.exit(1)


# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────

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


# ─────────────────────────────────────────────
# Database
# ─────────────────────────────────────────────

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
    """Serialize float list to bytes for SQLite BLOB storage."""
    return struct.pack(f"{len(embedding)}f", *embedding)


def deserialize_embedding(blob):
    """Deserialize bytes back to float list."""
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


# ─────────────────────────────────────────────
# Chunking
# ─────────────────────────────────────────────

def chunk_text(text, chunk_size=500, overlap=50):
    """
    Fixed-size character chunking with overlap.
    chunk_size ~ 125 tokens at ~4 chars/token.
    Returns list of (chunk_text, chunk_index) tuples.
    """
    text = text.strip()
    if not text:
        return []

    chunks = []
    start = 0
    index = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append((chunk, index))
            index += 1
        if end >= len(text):
            break
        start = end - overlap

    return chunks


# ─────────────────────────────────────────────
# Embedding
# ─────────────────────────────────────────────

def get_embedding(text, ollama_url, model):
    """Call Ollama embeddings API and return embedding vector."""
    url = f"{ollama_url.rstrip('/')}/api/embeddings"
    payload = {"model": model, "prompt": text}

    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()["embedding"]
    except requests.exceptions.ConnectionError:
        print(f"  ERROR: Cannot connect to Ollama at {ollama_url}")
        print("  Is Ollama running? Try: ollama serve")
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        print(f"  ERROR: Ollama API error: {e}")
        print(f"  Is '{model}' pulled? Try: ollama pull {model}")
        sys.exit(1)
    except KeyError:
        print("  ERROR: Unexpected Ollama response format")
        sys.exit(1)


def check_ollama(ollama_url, model):
    """Verify Ollama is running and model is available."""
    print(f"  Checking Ollama at {ollama_url}...")
    try:
        r = requests.get(f"{ollama_url.rstrip('/')}/api/tags", timeout=5)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        model_base = model.split(":")[0]
        if not any(m.startswith(model_base) for m in models):
            print(f"  WARNING: '{model}' not found in Ollama.")
            print(f"  Available models: {', '.join(models) or 'none'}")
            print(f"  Run: ollama pull {model}")
            sys.exit(1)
        print(f"  ✓ Ollama OK — model '{model}' available")
    except requests.exceptions.ConnectionError:
        print(f"  ERROR: Cannot reach Ollama at {ollama_url}")
        sys.exit(1)


# ─────────────────────────────────────────────
# Document layer detection
# ─────────────────────────────────────────────

def detect_layer(path_str):
    """Detect SSoT layer from file path (L0–L4 or root)."""
    parts = Path(path_str).parts
    for part in parts:
        if part.upper() in ("L0", "L1", "L2", "L3", "L4"):
            return part.upper()
    return "ROOT"


def file_hash(path):
    """MD5 hash of file contents for change detection."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


# ─────────────────────────────────────────────
# Indexing
# ─────────────────────────────────────────────

def needs_reindex(conn, path_str, current_mtime, current_hash):
    """Check if a file needs re-indexing based on mtime and hash."""
    row = conn.execute(
        "SELECT file_mtime, file_hash FROM index_meta WHERE source_path = ?",
        (path_str,)
    ).fetchone()

    if row is None:
        return True  # Never indexed
    stored_mtime, stored_hash = row
    return current_mtime != stored_mtime or current_hash != stored_hash


def index_file(conn, file_path, config, force=False):
    """Index a single markdown file. Returns (chunks_added, skipped)."""
    path_str = str(file_path)
    current_mtime = file_path.stat().st_mtime
    current_hash = file_hash(file_path)

    if not force and not needs_reindex(conn, path_str, current_mtime, current_hash):
        return 0, True  # Skipped

    # Read document
    try:
        text = file_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"  WARNING: Could not read {file_path}: {e}")
        return 0, False

    if not text.strip():
        return 0, False

    # Remove old chunks for this file
    conn.execute("DELETE FROM chunks WHERE source_path = ?", (path_str,))

    # Chunk the document
    chunks = chunk_text(text, config["chunkSize"], config["chunkOverlap"])
    if not chunks:
        return 0, False

    layer = detect_layer(path_str)
    count = 0

    for chunk_text_content, chunk_idx in chunks:
        embedding = get_embedding(
            chunk_text_content,
            config["ollamaUrl"],
            config["embeddingModel"]
        )
        embedding_blob = serialize_embedding(embedding)

        conn.execute(
            """INSERT INTO chunks (source_path, doc_layer, chunk_index, chunk_text, embedding)
               VALUES (?, ?, ?, ?, ?)""",
            (path_str, layer, chunk_idx, chunk_text_content, embedding_blob)
        )
        count += 1

    # Update index metadata
    conn.execute(
        """INSERT OR REPLACE INTO index_meta (source_path, file_mtime, chunk_count, file_hash, indexed_at)
           VALUES (?, ?, ?, ?, ?)""",
        (path_str, current_mtime, count, current_hash, datetime.now().isoformat())
    )

    conn.commit()
    return count, False


def index_all(config, full=False):
    """Walk the SSoT directory and index all markdown files."""
    ssot_root = Path(config["ssotRoot"]).expanduser()

    if not ssot_root.exists():
        print(f"ERROR: SSoT root not found: {ssot_root}")
        print("Is ResonantOS installed? Check config ssotRoot.")
        sys.exit(1)

    conn = get_db(config["dbPath"])

    md_files = list(ssot_root.rglob("*.md"))
    if not md_files:
        print(f"WARNING: No markdown files found in {ssot_root}")
        return

    print(f"\nIndexing SSoT documents from: {ssot_root}")
    print(f"Files found: {len(md_files)}")
    print(f"Mode: {'full re-index' if full else 'incremental'}\n")

    total_chunks = 0
    total_indexed = 0
    total_skipped = 0

    for file_path in sorted(md_files):
        rel = file_path.relative_to(ssot_root)
        chunks_added, skipped = index_file(conn, file_path, config, force=full)

        if skipped:
            print(f"  SKIP  {rel}")
            total_skipped += 1
        else:
            print(f"  INDEX {rel} → {chunks_added} chunks")
            total_indexed += 1
            total_chunks += chunks_added

    print(f"\n{'─'*50}")
    print(f"  Indexed : {total_indexed} files ({total_chunks} chunks)")
    print(f"  Skipped : {total_skipped} files (unchanged)")
    print(f"  DB      : {Path(config['dbPath']).expanduser()}")
    print(f"{'─'*50}\n")

    conn.close()


def show_stats(config):
    """Print index statistics."""
    db_path = Path(config["dbPath"]).expanduser()

    if not db_path.exists():
        print("No index found. Run: python rag-indexer.py")
        return

    conn = sqlite3.connect(str(db_path))

    total_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    total_docs = conn.execute("SELECT COUNT(*) FROM index_meta").fetchone()[0]

    print(f"\nRAG Index Statistics")
    print(f"{'─'*40}")
    print(f"  Documents indexed : {total_docs}")
    print(f"  Total chunks      : {total_chunks}")
    print(f"  Database          : {db_path}")

    print(f"\n  By layer:")
    rows = conn.execute(
        "SELECT doc_layer, COUNT(*) as n FROM chunks GROUP BY doc_layer ORDER BY doc_layer"
    ).fetchall()
    for layer, count in rows:
        print(f"    {layer:<8} {count} chunks")

    print(f"\n  Recently indexed:")
    rows = conn.execute(
        "SELECT source_path, chunk_count, indexed_at FROM index_meta ORDER BY indexed_at DESC LIMIT 5"
    ).fetchall()
    for path, count, ts in rows:
        short = Path(path).name
        print(f"    {short:<40} {count:>3} chunks  {ts[:19]}")

    print()
    conn.close()


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="ResonantOS RAG Indexer — index SSoT documents for semantic search"
    )
    parser.add_argument("--full", action="store_true", help="Force full re-index of all files")
    parser.add_argument("--stats", action="store_true", help="Show index statistics")
    parser.add_argument("--path", help="Override SSoT root path")
    parser.add_argument("--config", help="Path to config file")
    args = parser.parse_args()

    config = load_config(args.config)

    if args.path:
        config["ssotRoot"] = args.path

    if args.stats:
        show_stats(config)
        return

    check_ollama(config["ollamaUrl"], config["embeddingModel"])
    index_all(config, full=args.full)


if __name__ == "__main__":
    main()
