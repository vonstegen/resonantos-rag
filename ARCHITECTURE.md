# Architecture

## Overview

resonantos-rag is designed as a drop-in completion of ResonantOS's Layer 4 memory slot. It follows ResonantOS conventions wherever possible — same workspace paths, same config patterns, same extension pipeline.

---

## Components

### 1. Indexer (`indexer/rag-indexer.py`)

**Responsibility:** Convert SSoT documents into searchable vector embeddings.

**Pipeline:**
```
SSoT file (.md)
    → read raw text
    → split into chunks (fixed-size, token-approximate, with overlap)
    → for each chunk: POST to Ollama /api/embeddings
    → store (chunk_text, embedding, source_path, chunk_index, doc_layer) in SQLite
```

**Chunking strategy:** Fixed-size at 500 characters (~125 tokens) with 50-character overlap. This was chosen over semantic/heading-based chunking for the following reasons:
- Simpler to implement and explain
- Consistent retrieval performance regardless of document structure
- SSoT docs at this stage are short enough that fixed-size works well
- Easier to tune: adjust `chunkSize` and `chunkOverlap` in config

**Re-indexing:** The indexer tracks file modification times. Running it again only re-indexes files that have changed. A full re-index can be forced with `--full`.

**SQLite schema:**
```sql
CREATE TABLE chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_path TEXT NOT NULL,
    doc_layer TEXT,           -- L0, L1, L2, L3, L4
    chunk_index INTEGER,      -- position within document
    chunk_text TEXT NOT NULL,
    embedding BLOB NOT NULL,  -- float32 array, serialized
    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE index_meta (
    source_path TEXT PRIMARY KEY,
    file_mtime REAL,
    chunk_count INTEGER,
    indexed_at TIMESTAMP
);
```

---

### 2. Query Layer (`query/rag-query.py`)

**Responsibility:** Given an input string, return the top-k most semantically similar chunks.

**Pipeline:**
```
input string
    → POST to Ollama /api/embeddings (same model as indexer)
    → load all embeddings from SQLite
    → cosine similarity between input embedding and all chunk embeddings
    → filter by minScore threshold
    → return top-k results sorted by score
```

**Cosine similarity** is used rather than dot product because nomic-embed-text produces normalized vectors — cosine similarity is equivalent to dot product on normalized vectors and is the standard for this model.

**Performance note:** For small SSoT corpora (< 5,000 chunks), in-memory cosine similarity over all chunks is fast enough (~10–50ms). If the corpus grows significantly, consider adding an ANN index (e.g., `hnswlib`).

---

### 3. OpenClaw Extension (`extension/r-rag.js`)

**Responsibility:** Hook into OpenClaw's extension pipeline and inject RAG results into agent context.

**Integration point:** Runs after `r-awareness.js` in the extension chain. R-Awareness loads the full SSoT document on keyword match; r-rag.js injects the top-k semantically relevant chunks on top of that, drawn from the current conversation turn.

**Context injection format:**
```
[RAG: L2/ATHLETE.md — chunk 3/7 | score: 0.82]
... chunk text here ...

[RAG: L0/PHILOSOPHY.md — chunk 1/4 | score: 0.74]
... chunk text here ...
```

**Token budget:** Respects R-Awareness's 15K token budget. RAG results are injected after R-Awareness docs, consuming from the same budget. If the budget is exhausted, lower-scoring chunks are dropped.

---

### 4. Config (`config/rag-config.json`)

Deployed to `~/.openclaw/workspace/r-rag/config.json` on install.

All paths support `~` expansion. `ssotRoot` is auto-detected from the ResonantOS installer's known path (`~/.openclaw/workspace/resonantos-alpha/ssot`).

---

## Design Decisions

### Why SQLite and not Qdrant?

Lumen already has a Qdrant instance tunneled to the Open Brain VPS for the TriuneBrain memory system. This RAG layer deliberately uses local SQLite to:
- Keep it self-contained and easy to install
- Avoid dependency on the tunnel being active
- Make it trivially portable to any ResonantOS install
- Keep the corpus small enough that SQLite performs well

Qdrant integration is a natural future upgrade path.

### Why nomic-embed-text?

- Already recommended in the ResonantOS README
- Small (274MB), runs on GPU via Ollama
- 768-dimensional embeddings — good quality for document retrieval
- Fully local, no API key required

### Why not OpenClaw's built-in memory_search?

`memory_search` is a core OpenClaw tool but its embedding config is not exposed in `openclaw.json` or `.env`. After review of the OpenClaw source and ResonantOS codebase, there is no public API to configure its embedding provider. This layer therefore implements its own embedding pipeline using the same model.

---

## Future Improvements

- Heading-based semantic chunking for better boundary preservation
- Re-index trigger via OpenClaw cron (rather than manual)
- ANN index (hnswlib) for larger corpora
- Qdrant backend option for integration with Open Brain VPS
- Per-agent RAG databases (aligned with OpenClaw's multi-agent model)
- Streaming chunk injection rather than full-context injection
