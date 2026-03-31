#!/usr/bin/env python3
"""
test-query.py — ResonantOS RAG Test Suite

Tests the full pipeline: embedding → storage → retrieval.
Requires a live Ollama instance with nomic-embed-text.

Usage:
    python tests/test-query.py
    python tests/test-query.py --verbose
"""

import sys
import os
import json
import math
import struct
import sqlite3
import tempfile
import argparse
from pathlib import Path

# Add indexer to path
sys.path.insert(0, str(Path(__file__).parent.parent / "indexer"))
sys.path.insert(0, str(Path(__file__).parent.parent / "query"))

try:
    import requests
except ImportError:
    print("ERROR: 'requests' not installed. Run: pip install requests")
    sys.exit(1)


OLLAMA_URL = "http://localhost:11434"
EMBEDDING_MODEL = "nomic-embed-text"

PASS = "✓"
FAIL = "✗"
SKIP = "○"

results = []


def test(name, fn):
    try:
        fn()
        results.append((PASS, name, None))
        print(f"  {PASS}  {name}")
    except AssertionError as e:
        results.append((FAIL, name, str(e)))
        print(f"  {FAIL}  {name}")
        print(f"       {e}")
    except Exception as e:
        results.append((FAIL, name, str(e)))
        print(f"  {FAIL}  {name}")
        print(f"       Unexpected error: {e}")


# ─────────────────────────────────────────────
# Test: Ollama connectivity
# ─────────────────────────────────────────────

def test_ollama_running():
    r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
    assert r.status_code == 200, f"Ollama returned {r.status_code}"


def test_model_available():
    r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
    models = [m["name"] for m in r.json().get("models", [])]
    model_base = EMBEDDING_MODEL.split(":")[0]
    assert any(m.startswith(model_base) for m in models), \
        f"'{EMBEDDING_MODEL}' not found. Available: {models}"


def test_embedding_returns_vector():
    r = requests.post(f"{OLLAMA_URL}/api/embeddings", json={
        "model": EMBEDDING_MODEL,
        "prompt": "test embedding"
    }, timeout=30)
    assert r.status_code == 200, f"Embedding API returned {r.status_code}"
    data = r.json()
    assert "embedding" in data, "No 'embedding' key in response"
    assert isinstance(data["embedding"], list), "Embedding is not a list"
    assert len(data["embedding"]) > 0, "Embedding is empty"


def test_embedding_dimension():
    r = requests.post(f"{OLLAMA_URL}/api/embeddings", json={
        "model": EMBEDDING_MODEL,
        "prompt": "dimension test"
    }, timeout=30)
    emb = r.json()["embedding"]
    assert len(emb) == 768, f"Expected 768 dimensions, got {len(emb)}"


# ─────────────────────────────────────────────
# Test: Chunking
# ─────────────────────────────────────────────

def test_chunking_basic():
    sys.path.insert(0, str(Path(__file__).parent.parent / "indexer"))
    from rag_indexer import chunk_text

    text = "word " * 200  # ~1000 chars
    chunks = chunk_text(text, chunk_size=500, overlap=50)
    assert len(chunks) >= 2, f"Expected multiple chunks, got {len(chunks)}"


def test_chunking_overlap():
    from rag_indexer import chunk_text

    text = "A" * 600
    chunks = chunk_text(text, chunk_size=500, overlap=100)
    # With 100 char overlap, chunk 2 should start at 400 not 500
    assert len(chunks) == 2, f"Expected 2 chunks, got {len(chunks)}"


def test_chunking_empty():
    from rag_indexer import chunk_text

    chunks = chunk_text("", chunk_size=500, overlap=50)
    assert chunks == [], f"Expected empty list for empty text, got {chunks}"


def test_chunking_short():
    from rag_indexer import chunk_text

    text = "Short text."
    chunks = chunk_text(text, chunk_size=500, overlap=50)
    assert len(chunks) == 1, f"Expected 1 chunk for short text, got {len(chunks)}"
    assert chunks[0][0] == "Short text."


# ─────────────────────────────────────────────
# Test: SQLite serialization
# ─────────────────────────────────────────────

def test_embedding_serialization():
    from rag_indexer_lib import serialize_embedding, deserialize_embedding

    original = [0.1, 0.2, 0.3, -0.5, 0.99]
    blob = serialize_embedding(original)
    recovered = deserialize_embedding(blob)
    for a, b in zip(original, recovered):
        assert abs(a - b) < 1e-5, f"Serialization mismatch: {a} vs {b}"


# ─────────────────────────────────────────────
# Test: Cosine similarity
# ─────────────────────────────────────────────

def test_cosine_identical():
    from rag_query import cosine_similarity

    v = [1.0, 0.0, 0.0]
    score = cosine_similarity(v, v)
    assert abs(score - 1.0) < 1e-6, f"Identical vectors should have score 1.0, got {score}"


def test_cosine_orthogonal():
    from rag_query import cosine_similarity

    a = [1.0, 0.0, 0.0]
    b = [0.0, 1.0, 0.0]
    score = cosine_similarity(a, b)
    assert abs(score) < 1e-6, f"Orthogonal vectors should have score 0.0, got {score}"


def test_cosine_opposite():
    from rag_query import cosine_similarity

    a = [1.0, 0.0, 0.0]
    b = [-1.0, 0.0, 0.0]
    score = cosine_similarity(a, b)
    assert abs(score - (-1.0)) < 1e-6, f"Opposite vectors should have score -1.0, got {score}"


# ─────────────────────────────────────────────
# Test: End-to-end (index + query)
# ─────────────────────────────────────────────

def test_end_to_end():
    """Full pipeline: write test docs, index them, query, verify results."""
    from rag_indexer import index_all
    from rag_query import query
    from rag_indexer_lib import load_config

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test SSoT docs
        ssot_dir = Path(tmpdir) / "ssot" / "L2"
        ssot_dir.mkdir(parents=True)

        (ssot_dir / "ATHLETE.md").write_text(
            "# Athlete Profile\n\nGS skiing technique. Knee protection during high-speed turns. "
            "Off-season strength training for leg stability. Managing knee pain between races."
        )
        (ssot_dir / "OPERATOR.md").write_text(
            "# Book Arbitrage Operations\n\nScouting used books on Amazon. "
            "Price gap analysis between buy and sell markets. Inventory management and logistics."
        )

        db_path = str(Path(tmpdir) / "test.db")

        config = load_config()
        config["ssotRoot"] = str(ssot_dir.parent)
        config["dbPath"] = db_path
        config["chunkSize"] = 300
        config["chunkOverlap"] = 30
        config["topK"] = 3
        config["minScore"] = 0.3  # Lower threshold for test

        # Index
        index_all(config, full=True)

        # Query — should find ATHLETE doc for knee pain
        results = query("knee pain skiing", config)
        assert len(results) > 0, "Expected at least one result for 'knee pain skiing'"

        top = results[0]
        assert "ATHLETE" in top["source_name"], \
            f"Expected ATHLETE doc to rank first, got: {top['source_name']}"
        assert top["score"] >= 0.3, f"Score too low: {top['score']}"

        # Query — should find OPERATOR doc for book pricing
        results2 = query("book price analysis", config)
        assert len(results2) > 0, "Expected at least one result for 'book price analysis'"

        top2 = results2[0]
        assert "OPERATOR" in top2["source_name"], \
            f"Expected OPERATOR doc to rank first, got: {top2['source_name']}"


# ─────────────────────────────────────────────
# Run
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="ResonantOS RAG test suite")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    print("\nResonantOS RAG — Test Suite")
    print("─" * 50)

    print("\n  Ollama connectivity")
    test("Ollama is running", test_ollama_running)
    test("nomic-embed-text is available", test_model_available)
    test("Embedding API returns vector", test_embedding_returns_vector)
    test("Embedding dimension is 768", test_embedding_dimension)

    print("\n  Chunking")
    test("Basic chunking produces multiple chunks", test_chunking_basic)
    test("Overlap is respected", test_chunking_overlap)
    test("Empty text returns empty list", test_chunking_empty)
    test("Short text returns single chunk", test_chunking_short)

    print("\n  Serialization")
    test("Embedding round-trips through SQLite BLOB", test_embedding_serialization)

    print("\n  Cosine similarity")
    test("Identical vectors → score 1.0", test_cosine_identical)
    test("Orthogonal vectors → score 0.0", test_cosine_orthogonal)
    test("Opposite vectors → score -1.0", test_cosine_opposite)

    print("\n  End-to-end pipeline")
    test("Index + query returns correct documents", test_end_to_end)

    # Summary
    passed = sum(1 for r in results if r[0] == PASS)
    failed = sum(1 for r in results if r[0] == FAIL)

    print(f"\n{'─' * 50}")
    print(f"  {passed} passed · {failed} failed")
    print()

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
