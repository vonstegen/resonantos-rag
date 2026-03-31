# resonantos-rag

> **RAG (Retrieval-Augmented Generation) layer for ResonantOS** — completing the 4-layer memory stack.

Built by [@vonstegen](https://github.com/vonstegen) as a community contribution to [ResonantOS](https://github.com/ResonantOS/resonantos-alpha).

---

## What This Is

ResonantOS documents a 4-layer memory stack:

| Layer | Component | Status |
|-------|-----------|--------|
| 1 | `MEMORY.md` — always-in-context long-term memory | ✅ Built |
| 2 | R-Awareness headers — recent decision injection | ✅ Built |
| 3 | LCM — lossless context compression | ✅ Built |
| 4 | **RAG — semantic vector search** | ❌ Not yet implemented |

This project implements Layer 4.

Instead of loading entire SSoT documents on keyword match, RAG understands the *meaning* of what you're talking about and injects only the most relevant chunks — more precise, more token-efficient.

**Example:**
- R-Awareness (keyword): mention "skiing" → loads all of `L2/ATHLETE.md`
- RAG (semantic): mention "knee pain mid-season" → loads only the injury-relevant section of `L2/ATHLETE.md`

---

## How It Works

```
SSoT Documents (L0–L4)
        ↓
  [rag-indexer.py]          Chunks docs → embeds via Ollama → stores in SQLite
        ↓
   rag.db (SQLite)          Vector store: chunks + embeddings + metadata
        ↓
  [rag-query.py]            Embeds query → cosine similarity → returns top-k chunks
        ↓
   [r-rag.js]               OpenClaw extension — injects results into agent context
```

Embeddings are generated locally via [nomic-embed-text](https://ollama.com/library/nomic-embed-text) running on Ollama. No cloud dependencies. Everything stays on your machine.

---

## Prerequisites

- [ResonantOS](https://github.com/ResonantOS/resonantos-alpha) installed
- [OpenClaw](https://github.com/openclaw/openclaw) running
- [Ollama](https://ollama.com) installed with `nomic-embed-text` pulled:
  ```bash
  ollama pull nomic-embed-text
  ```
- Python 3.8+
- Node.js 18+

---

## Install

```bash
git clone https://github.com/vonstegen/resonantos-rag.git ~/resonantos-rag
node ~/resonantos-rag/install.js
```

The installer will:
1. Check dependencies (Ollama, nomic-embed-text, Python, pip)
2. Install Python dependencies into a venv
3. Run the initial index of your SSoT documents
4. Install the `r-rag.js` extension into OpenClaw
5. Register the RAG config in your workspace

---

## Configuration

Edit `~/.openclaw/workspace/r-rag/config.json`:

```json
{
  "ollamaUrl": "http://localhost:11434",
  "embeddingModel": "nomic-embed-text",
  "ssotRoot": "~/.openclaw/workspace/resonantos-alpha/ssot",
  "dbPath": "~/.openclaw/workspace/r-rag/rag.db",
  "chunkSize": 500,
  "chunkOverlap": 50,
  "topK": 5,
  "minScore": 0.65
}
```

| Key | Description | Default |
|-----|-------------|---------|
| `ollamaUrl` | Ollama API endpoint | `http://localhost:11434` |
| `embeddingModel` | Model for embeddings | `nomic-embed-text` |
| `ssotRoot` | Path to your SSoT documents | auto-detected |
| `dbPath` | SQLite database location | `~/.openclaw/workspace/r-rag/rag.db` |
| `chunkSize` | Tokens per chunk | `500` |
| `chunkOverlap` | Overlap between chunks | `50` |
| `topK` | Results to inject per query | `5` |
| `minScore` | Minimum similarity threshold (0–1) | `0.65` |

---

## Manual Usage

**Re-index your SSoT documents:**
```bash
cd ~/resonantos-rag
source venv/bin/activate
python indexer/rag-indexer.py
```

**Query from the command line:**
```bash
python query/rag-query.py "knee pain during ski season"
```

**Run tests:**
```bash
python tests/test-query.py
```

---

## Architecture

See [ARCHITECTURE.md](./ARCHITECTURE.md) for design decisions, chunk strategy rationale, and extension hook documentation.

---

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md). PRs welcome — especially around chunk strategies, re-indexing triggers, and OpenClaw integration depth.

---

## Status

**Alpha — built alongside ResonantOS v0.5.1**

Tested on:
- Ubuntu 24 (WSL2) + RTX 3080 Ti + Ollama GPU inference
- nomic-embed-text:latest (274MB)

---

## Community

Built for and with the [ResonantOS community](https://discord.gg/MRESQnf4R4).

If you're running ResonantOS and want semantic memory — this is your Layer 4.
