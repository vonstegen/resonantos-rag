# Contributing

This project is a community contribution to [ResonantOS](https://github.com/ResonantOS/resonantos-alpha) — building the Layer 4 RAG memory component that the project documents but hasn't shipped yet.

PRs, issues, and discussion welcome.

---

## Getting Started

```bash
git clone https://github.com/vonstegen/resonantos-rag.git
cd resonantos-rag
python -m venv venv
source venv/bin/activate
pip install -r indexer/requirements.txt
```

Run the tests against a live Ollama instance:
```bash
python tests/test-query.py
```

---

## Areas Most Needing Contribution

**Chunk strategies**
The current fixed-size chunker works but loses document structure. A heading-aware semantic chunker would improve retrieval quality for well-structured SSoT docs.

**Re-index triggers**
Currently manual. An inotify watcher or OpenClaw cron hook would make re-indexing automatic when SSoT files change.

**Qdrant backend**
SQLite works for small corpora. A Qdrant backend option would enable integration with the Open Brain VPS and larger document sets.

**Windows/macOS testing**
Developed and tested on Ubuntu (WSL2). Testing on native Windows and macOS welcome.

**Performance benchmarking**
Cosine similarity over all chunks works for small corpora. At what corpus size does it degrade? When should ANN indexing kick in?

---

## Conventions

- Follow ResonantOS file and path conventions
- Config lives at `~/.openclaw/workspace/r-rag/config.json`
- Keep the installer pattern consistent with `resonantos-alpha/install.js`
- Document design decisions in `ARCHITECTURE.md`
- One PR per feature — keep changes focused

---

## Reporting Issues

Please include:
- OS and environment (WSL2, native Linux, macOS)
- ResonantOS version (`cat ~/resonantos-alpha/VERSION`)
- OpenClaw version (`openclaw --version`)
- Ollama version (`ollama --version`)
- Full error output

---

## Community

Discussion happens in the [ResonantOS Discord](https://discord.gg/MRESQnf4R4).
