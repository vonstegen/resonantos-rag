# Build & Test Log — resonantos-rag

**Date:** 2026-03-31  
**Author:** [@vonstegen](https://github.com/vonstegen)  
**Platform:** Lumen — Gigabyte X570S AORUS MASTER, RTX 3080 Ti, 64GB RAM, WSL2 (Ubuntu 24)  
**ResonantOS version:** v0.5.3  
**OpenClaw version:** v2026.3.23-2  

---

## Objective

Complete ResonantOS's documented but unimplemented Layer 4 memory stack — RAG (Retrieval-Augmented Generation) — using local Ollama embeddings and semantic vector search over SSoT documents.

The ResonantOS README and GETTING-STARTED.md both document a 4-layer memory stack:

| Layer | Component | State at start |
|-------|-----------|----------------|
| 1 | MEMORY.md | ✅ Built |
| 2 | R-Awareness headers | ✅ Built |
| 3 | LCM compression | ✅ Built |
| 4 | RAG — semantic vector search | ❌ Not implemented |

---

## Phase 1 — Pre-Install Audit

**Principle:** Read the installer before running it. Every time.

Before touching the system, `install.js` (299 lines) was read in full via Claude Code. Key findings:

- Installer would clone to `~/resonantos-alpha/` and copy extensions into `~/.openclaw/agents/main/agent/extensions/`
- Workspace templates (SOUL.md, IDENTITY.md, USER.md, AGENTS.md, TOOLS.md) would be **skipped if already present** — confirmed safe
- `openclaw.json` would receive one addition: setup agent entry — confirmed surgical
- **Logician step would fail gracefully on Linux** — `mangle-server.exe` is Windows-only binary, non-fatal

**Pre-flight actions taken:**
- Backed up `openclaw.json` to `openclaw.json.pre-ros`
- Confirmed `~/.openclaw/agents/main/agent/extensions/` did not exist — no files at risk

---

## Phase 2 — ResonantOS Installation

**Command:** `node ~/resonantos-alpha-preview/install.js`

**First failure:**
```
ERROR: pip3/pip is required (should come with Python 3).
```
**Fix:** `sudo apt install python3-pip python3-venv -y`

**Second run — clean:**
- Dependencies: OK
- Repo: cloned to `~/resonantos-alpha/`
- Extensions: `r-memory.js`, `r-awareness.js`, `gateway-lifecycle.js` installed
- Workspace templates: MEMORY.md created (new), all others correctly skipped
- R-Awareness config: written
- Setup Agent: registered in `openclaw.json`
- Logician: skipped (Linux — expected, graceful)
- Dashboard venv: created, Flask/psutil installed

**`openclaw.json` diff:** exactly one change — setup agent added to `agents.list`. Nothing else modified.

---

## Phase 3 — RAG Discovery

**Hypothesis:** RAG is configured somewhere in ResonantOS or OpenClaw.

**Investigation:**
1. Searched `ResonantOS/resonantos-alpha` GitHub for `ollama`, `embed`, `nomic` — **zero results**
2. Searched `openclaw/openclaw` source — no embedding config found in `openclaw.json` or `.env.example`
3. Examined `~/.openclaw/agents/main/agent/extensions/r-memory.js` — pure conversation compression, no embedding
4. Discovered `~/.openclaw/memory/main.sqlite` — **21K+ indexed chunks** using SQLite FTS5 full-text search (not vectors)
5. Found `mcp-server/src/index.js` — hardcoded macOS paths (`/Users/augmentor/`) that **silently break on Linux**

**Conclusion:** ResonantOS v0.5.3 has:
- FTS5 keyword search via Memory Bridge MCP
- No vector embedding layer

**Decision:** Build it.

---

## Phase 4 — Embedding Provider Setup

**Model:** `nomic-embed-text` — recommended in ResonantOS README, 274MB, 768 dimensions

**Ollama not installed on Lumen:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull nomic-embed-text
```

Output confirmed: `>>> Nvidia GPU detected.` — RTX 3080 Ti in use.

---

## Phase 5 — resonantos-rag Build

**Design decisions:**
- SQLite vector store (not Qdrant) — self-contained, no external dependencies, portable
- Fixed-size chunking at 500 chars with 50-char overlap — simple, predictable, tunable
- Cosine similarity search — standard for normalised nomic-embed-text vectors
- OpenClaw extension hook — injects results before LLM call

**Files built:**

| File | Purpose |
|------|---------|
| `indexer/rag-indexer.py` | Chunks SSoT docs, embeds via Ollama, stores in SQLite |
| `indexer/rag_indexer_lib.py` | Shared config + DB utilities |
| `query/rag-query.py` | Cosine similarity search — CLI + JSON + inject formats |
| `extension/r-rag.js` | OpenClaw extension hook |
| `config/rag-config.json` | Default configuration |
| `tests/test-query.py` | Full test suite |
| `install.js` | Mirrors ResonantOS install pattern |

**Repo:** `github.com/vonstegen/resonantos-rag`

---

## Phase 6 — Test Suite Execution

**Setup issue:** Python import error — hyphenated filenames (`rag-indexer.py`) can't be imported directly.

**Fix:** Symlinks created:
```bash
indexer/rag_indexer.py -> indexer/rag-indexer.py
query/rag_query.py -> query/rag-query.py
```

**Results: 13/13 tests passed**

| Test Group | Tests | Result |
|------------|-------|--------|
| Ollama connectivity | 4 | ✅ |
| Chunking logic | 4 | ✅ |
| SQLite serialisation | 1 | ✅ |
| Cosine similarity | 3 | ✅ |
| End-to-end pipeline | 1 | ✅ |

---

## Phase 7 — MCP Path Bug

**Bug found:** `mcp-server/src/index.js` had three hardcoded macOS paths:

| Constant | Old (macOS) | New (Lumen) |
|----------|-------------|-------------|
| MEMORY_DB | `/Users/augmentor/.openclaw/memory/main.sqlite` | `/home/avonstegen/.openclaw/memory/main.sqlite` |
| SSOT_DIR | `/Users/augmentor/resonantos-augmentor/ssot` | `/home/avonstegen/resonantos-alpha/ssot` |
| RESEARCH_DIR | `/Users/augmentor/resonantos-augmentor/research` | `/home/avonstegen/resonantos-alpha/research` |

Note: also fixed `resonantos-augmentor` → `resonantos-alpha` (incorrect repo name).

**Impact:** Memory Bridge MCP silently broken on any Linux install.  
**Fix:** `sed -i 's|/Users/augmentor|/home/avonstegen|g'` + manual repo name correction.  
**Status:** Reported to upstream for fix.

---

## Phase 8 — SSoT Document Creation

R-Awareness had 35 keyword mappings configured but all L2 documents were `.gitkeep` placeholders. Created 7 Pillar documents:

- `L2/BUILDER.md` — AI Systems & Infrastructure
- `L2/THINKER.md` — Austrian economics, Biblical Unitarian theology, LYT method
- `L2/OPERATOR.md` — Book Arbitrage Agent, automation
- `L2/ATHLETE.md` — GS skiing, strength training, indoor biking
- `L2/CRAFTSMAN.md` — CAD, timber framing, building design
- `L2/PHILOSOPHER.md` — AI ethics, economic freedom, individual sovereignty
- `L2/INVESTOR.md` — 19-asset crypto portfolio, sound money thesis

---

## Phase 9 — RAG Indexing

**First run issue:** Config file at `~/.openclaw/workspace/r-rag/config.json` didn't exist — indexer ran against default paths, database stored in different location than query was searching.

**Fix:** Explicitly created config with absolute paths (not `~`), ran indexer with `--config` flag.

**Index result:**
- 56 documents, 674 chunks
- L1: 607 chunks, L2: 62 chunks, L4: 5 chunks

**Threshold tuning:**

Default `minScore: 0.65` caused OPERATOR.md to miss on "book arbitrage pricing strategy" query (scored 0.5257). Lowered to `0.50`.

**Sanity queries — final results:**

| Query | Top Result | Score |
|-------|-----------|-------|
| "book arbitrage pricing strategy" | OPERATOR.md (L2) | 0.5257 |
| "strength training for skiing" | ATHLETE.md (L2) | 0.7278 |
| "TriuneBrain distributed memory architecture" | BUILDER.md (L2) | 0.6248 |

---

## Phase 10 — Extension Integration

### Bug 1: Wrong Module System

**Symptom:** r-rag.js installed in extensions directory but RAG content not appearing in responses.

**Root cause:** r-rag.js was written using ESM module syntax. OpenClaw requires CommonJS.

| Item | Wrong (original) | Correct (fixed) |
|------|-----------------|-----------------|
| Module system | `export async function onTurn(ctx)` | `module.exports = function(api)` |
| Hook name | `onTurn` | `api.on("before_agent_start", ...)` |
| Injection method | `ctx.injectAfter(injection)` | `return { systemPrompt }` |

---

### Bug 2: Extensions Not Auto-Loaded

**Symptom:** After fixing module system, extension still not firing.

**Root cause:** Files in `~/.openclaw/agents/main/agent/extensions/` are **not auto-loaded**. OpenClaw requires:
1. Plugin directory at `~/.openclaw/extensions/<name>/`
2. `openclaw.plugin.json` manifest file with `id`, `main`, `format`, `configSchema`
3. Registration in `openclaw.json` under `plugins.entries` and `plugins.installs`

**Fix:** Created plugin manifest and registered in `openclaw.json`. Extension log then confirmed:
```
[r-rag] Extension registered on before_agent_start
```

---

### Bug 3: Config Path Resolution

**Symptom:** Extension registered but returning empty results.

**Root cause:** The `--config` flag wasn't being passed to the `rag-query.py` subprocess, so it used default path resolution which didn't find the database.

**Fix:** Added explicit `--config /home/avonstegen/.openclaw/workspace/r-rag/config.json` to the `execSync` call.

---

## Phase 11 — Production Validation

**Test message via Slack:** *"Tell me about my strength training approach for skiing"*

**Gateway log trace:**
```
[r-rag] before_agent_start FIRED, prompt length: 551
[r-rag] R-RAG v0.2.0 init — enabled, minScore 0.5, topK 5
[r-rag] Paths verified — Python, script, config, DB all found
[r-rag] Query: "Tell me about my strength training..."
[r-rag] Execution: 1.27s
[r-rag] Result: 5 chunks returned and injected into system prompt
```

**Lumen's response (via Slack):**
> *"Interesting — the RAG module is working. It injected ATHLETE.md chunks at the start of this session. Here's what it returned: Strength Training for Skiing: year-round compound movements, posterior chain and single-leg stability as focus, skiing performance as the north star..."*
> 
> *"The RAG layer is doing the heavy lifting here, not the search tool. That's probably useful signal for what you're building."*

ATHLETE.md content confirmed in response. Scores: 0.72–0.75. **Full stack validated.**

---

## Phase 12 — Logician Setup

The ResonantOS dashboard showed `production_rules.mg not found`.

**Build:**
- Installed Go 1.22.2 (apt version too old — installed from go.dev/dl)
- Built `mangle-server` binary from source (16MB)
- Created `production_rules.mg` from 4 of 5 templates

**Rule excluded:** `gateway-lifecycle.mg` — requires `TASK-STATE.json` which doesn't exist on fresh install. Enabling it would block gateway restarts. Deferred.

**Rules enabled:**
- `agent-registry.mg` — trust levels for orchestrator/coder/researcher/tester
- `cost-policy.mg` — blocks expensive models on routine tasks
- `spawn-control.mg` — prevents privilege escalation between agents
- `tool-permissions.mg` — dangerous tool access requires trust ≥ 3

**Dashboard issue:** Dashboard expected Unix socket at `/tmp/mangle.sock`, not TCP.

**Fix:** `--mode unix --sock-addr /tmp/mangle.sock`

**Result:** Dashboard reports `"status": "healthy", "ok": true`, 66 facts loaded.

**systemd service created** — persistent across reboots.

---

## Final System State

All services persistent via systemd:

| Service | Port/Socket | Status |
|---------|-------------|--------|
| OpenClaw gateway | :18789 | ✅ enabled, active |
| Shield daemon | :9999 | ✅ running |
| Dashboard | :19100 (0.0.0.0) | ✅ Tailscale accessible |
| Logician | /tmp/mangle.sock | ✅ enabled, active, 66 facts |
| Ollama | :11434 | ✅ enabled, GPU inference |
| openmemory-tunnel | :6333 | ✅ enabled, 7h+ uptime |

Memory stack complete:

| Layer | Component | Status |
|-------|-----------|--------|
| 1 | MEMORY.md | ✅ Populated |
| 2 | R-Awareness — 35 keywords | ✅ Live injection |
| 3 | LCM compression | ✅ Active |
| 4 | RAG — 674 chunks | ✅ Production validated |

---

## Bugs Reported Upstream

1. **MCP server hardcoded paths** — `mcp-server/src/index.js` has `/Users/augmentor/` macOS paths. Silently breaks Memory Bridge on any Linux install.

2. **Shield daemon path** — README and install docs reference `shield/shield.py`. Correct path is `shield/daemon.py`.

3. **`watchdog` missing from requirements** — Shield daemon requires `watchdog` Python package but it's not in any requirements file.

4. **RAG Layer 4 not implemented** — documented in README, GETTING-STARTED.md, and feature table but no implementation shipped. This project is the implementation.

---

## Key Learnings

**On OpenClaw extensions:**
- Extensions require a `openclaw.plugin.json` manifest and registration in `openclaw.json` — copying a `.js` file to the extensions directory is not sufficient
- CommonJS (`module.exports`) required — ESM exports not supported
- Hook name is `before_agent_start` — not `onTurn`, not `onMessage`
- Injection via `return { systemPrompt }` — not `ctx.injectAfter()`

**On ResonantOS alpha:**
- FTS5 (Memory Bridge) and RAG (this project) are complementary — keyword matching vs semantic matching
- SSoT L2–L4 layers ship empty — content is the user's responsibility
- `coldStartOnly: true` is the default — must be set to `false` for mid-conversation keyword injection
- Dashboard gateway connection requires `websocket-client` Python package

**On embedding:**
- `nomic-embed-text` produces 768-dimensional vectors
- `minScore: 0.50` works better than default `0.65` for small SSoT corpora
- Absolute paths required in config when called from Node.js subprocess

**On Go builds:**
- `apt install golang-go` ships Go 1.18 on Ubuntu 24 — too old
- Install from `go.dev/dl` for current version
- `export PATH=$PATH:/usr/local/go/bin` required in shell before build

---

## Repository

**github.com/vonstegen/resonantos-rag**

Commit history:
```
4f35d9c  feat: initial implementation of ResonantOS RAG Layer 4
1dc70fa  refactor: organise files into correct subdirectory structure
a64ab44  feat: add shared indexer library
35b9c97  feat: add Python requirements file
5ad7636  fix: add Python import symlinks for hyphenated filenames
cdb741d  docs: clarify FTS5 vs vector search distinction, note MCP path bug
<final>  fix: production-validated r-rag.js — CommonJS, OpenClaw plugin API
```

---

## Additional Bugs Found (2026-04-02)

### Bug 8: OpenClaw sub-agents require explicit Ollama auth profile
When switching a sub-agent (e.g. setup agent) from Anthropic to Ollama,
the sub-agent's auth-profiles.json must contain an explicit Ollama entry:
```json
"ollama:default": { "type": "api_key", "provider": "ollama", "key": "ollama" }
```
Without this, sub-agents fail with "No API key found for provider ollama"
even though the main agent handles keyless Ollama correctly.
**Fix:** Add ollama:default profile to each sub-agent's auth-profiles.json.

### Bug 9: Setup agent model not updated when gateway primary model changes
The model set for the setup agent (`agents.list[].model` in openclaw.json)
is independent of `agents.defaults.model.primary`. Switching the primary
gateway model to `ollama/qwen3:14b` does not cascade to the setup agent —
it must be updated separately via the dashboard API or by editing
openclaw.json directly. The setup agent was still set to
`anthropic/claude-sonnet-4-6` after the gateway model was changed.
**Fix:** Update setup agent model explicitly:
```bash
curl -s -X PUT http://localhost:19100/api/agents/setup/model \
  -H "Content-Type: application/json" \
  -d '{"model": "ollama/qwen3:14b"}'
```
Then add the Ollama auth profile (Bug 8) since the setup agent's auth
store doesn't inherit from the main agent.

## Additional Bugs Found (2026-04-06)

### Bug 10: WebSocket URL hardcoded in setup dashboard
`templates/setup.html:1238` — WebSocket URL hardcoded to `ws://127.0.0.1:18789`
instead of using `window.location.hostname`. This caused the dashboard to fail
when accessed remotely via Tailscale, as the browser would try to connect to
localhost instead of the remote node.
**Fix:** Use dynamic host: `ws://${window.location.hostname}:18789` so the
dashboard works correctly regardless of how it's accessed (local or remote).

### Bug 11: GW_HOST and GW_PORT hardcoded in server_v2.py
`server_v2.py:145-147` — GW_HOST and GW_PORT were hardcoded instead of
reading from environment variables. This prevented flexible deployment
scenarios where the gateway host/port needed to differ from defaults.
**Fix:** Read from `GW_HOST`/`GW_PORT` env vars with fallback to defaults:
```python
GW_HOST = os.environ.get('GW_HOST', '127.0.0.1')
GW_PORT = int(os.environ.get('GW_PORT', 18789))
```
