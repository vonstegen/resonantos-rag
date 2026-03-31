#!/usr/bin/env python3
"""
rag-query.py — ResonantOS RAG Layer 4
Query the vector store for semantically similar document chunks.

Usage:
    python rag-query.py "knee pain during ski season"
    python rag-query.py "book arbitrage pricing strategy" --top 3
    python rag-query.py "my values and philosophy" --layer L0
    python rag-query.py "what did I decide about TriuneBrain" --json
"""

import os
import sys
import json
import math
import struct
import sqlite3
import argparse
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: 'requests' not installed. Run: pip install requests")
    sys.exit(1)

# Shared config loader — same as indexer
sys.path.insert(0, str(Path(__file__).parent.parent / "indexer"))
from rag_indexer_lib import load_config, get_db, deserialize_embedding, serialize_embedding


# ─────────────────────────────────────────────
# Embedding
# ─────────────────────────────────────────────

def get_embedding(text, ollama_url, model):
    url = f"{ollama_url.rstrip('/')}/api/embeddings"
    payload = {"model": model, "prompt": text}
    try:
        r = requests.post(url, json=payload, timeout=30)
        r.raise_for_status()
        return r.json()["embedding"]
    except requests.exceptions.ConnectionError:
        print(f"ERROR: Cannot connect to Ollama at {ollama_url}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Embedding failed: {e}")
        sys.exit(1)


# ─────────────────────────────────────────────
# Similarity
# ─────────────────────────────────────────────

def cosine_similarity(a, b):
    """Cosine similarity between two float vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


# ─────────────────────────────────────────────
# Query
# ─────────────────────────────────────────────

def query(text, config, top_k=None, min_score=None, layer_filter=None):
    """
    Query the vector store for chunks similar to text.

    Returns list of dicts:
        {
            "score": float,
            "source_path": str,
            "doc_layer": str,
            "chunk_index": int,
            "chunk_text": str,
            "source_name": str   (filename only)
        }
    """
    top_k = top_k or config["topK"]
    min_score = min_score if min_score is not None else config["minScore"]

    db_path = Path(config["dbPath"]).expanduser()
    if not db_path.exists():
        print("ERROR: No index found. Run: python indexer/rag-indexer.py")
        sys.exit(1)

    # Embed the query
    query_embedding = get_embedding(text, config["ollamaUrl"], config["embeddingModel"])

    # Load chunks from SQLite
    conn = sqlite3.connect(str(db_path))

    if layer_filter:
        rows = conn.execute(
            "SELECT source_path, doc_layer, chunk_index, chunk_text, embedding FROM chunks WHERE doc_layer = ?",
            (layer_filter.upper(),)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT source_path, doc_layer, chunk_index, chunk_text, embedding FROM chunks"
        ).fetchall()

    conn.close()

    if not rows:
        return []

    # Score all chunks
    results = []
    for source_path, doc_layer, chunk_index, chunk_text, embedding_blob in rows:
        chunk_embedding = deserialize_embedding(embedding_blob)
        score = cosine_similarity(query_embedding, chunk_embedding)

        if score >= min_score:
            results.append({
                "score": round(score, 4),
                "source_path": source_path,
                "doc_layer": doc_layer,
                "chunk_index": chunk_index,
                "chunk_text": chunk_text,
                "source_name": Path(source_path).name,
            })

    # Sort by score descending, take top-k
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


def format_results(results, query_text):
    """Human-readable output for CLI use."""
    if not results:
        print(f"\nNo results above threshold for: \"{query_text}\"\n")
        return

    print(f"\nQuery: \"{query_text}\"")
    print(f"Results: {len(results)}\n")
    print("─" * 60)

    for i, r in enumerate(results, 1):
        print(f"\n[{i}] {r['source_name']} — {r['doc_layer']} | score: {r['score']}")
        print(f"    chunk {r['chunk_index']} of {r['source_path']}")
        print()
        # Indent chunk text
        for line in r["chunk_text"].splitlines():
            print(f"    {line}")
        print()

    print("─" * 60)


def format_context_injection(results):
    """
    Format results for injection into OpenClaw context.
    This is the format r-rag.js will use.
    """
    if not results:
        return ""

    lines = []
    for r in results:
        lines.append(f"[RAG: {r['source_name']} — {r['doc_layer']} chunk {r['chunk_index']} | score: {r['score']}]")
        lines.append(r["chunk_text"])
        lines.append("")

    return "\n".join(lines)


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="ResonantOS RAG Query — semantic search over SSoT documents"
    )
    parser.add_argument("query", help="Query string")
    parser.add_argument("--top", type=int, help="Number of results (default: from config)")
    parser.add_argument("--min-score", type=float, help="Minimum similarity score (0–1)")
    parser.add_argument("--layer", help="Filter by SSoT layer (L0, L1, L2, L3, L4)")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")
    parser.add_argument("--inject", action="store_true", help="Output in context injection format")
    parser.add_argument("--config", help="Path to config file")
    args = parser.parse_args()

    config = load_config(args.config)

    results = query(
        args.query,
        config,
        top_k=args.top,
        min_score=args.min_score,
        layer_filter=args.layer,
    )

    if args.json_output:
        print(json.dumps(results, indent=2))
    elif args.inject:
        print(format_context_injection(results))
    else:
        format_results(results, args.query)


if __name__ == "__main__":
    main()
