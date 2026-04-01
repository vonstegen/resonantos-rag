/**
 * r-rag.js — ResonantOS RAG Extension for OpenClaw
 * @version 0.2.0
 * @date 2026-03-31
 *
 * Hooks into the OpenClaw extension pipeline to inject semantically
 * relevant SSoT chunks into the agent's context window.
 *
 * Runs AFTER r-awareness.js — enriches keyword-triggered doc loading
 * with precise semantic chunk injection.
 *
 * Hook: before_agent_start — query RAG, inject into systemPrompt
 *
 * Install location: ~/.openclaw/agents/main/agent/extensions/r-rag.js
 */

const { execSync } = require("child_process");
const fs = require("fs");
const path = require("path");
const os = require("os");

// ─────────────────────────────────────────────
// Config
// ─────────────────────────────────────────────

const CONFIG_PATH = path.join(os.homedir(), ".openclaw", "workspace", "r-rag", "config.json");
const DEFAULT_CONFIG = {
  ollamaUrl: "http://localhost:11434",
  embeddingModel: "nomic-embed-text",
  dbPath: path.join(os.homedir(), ".openclaw", "workspace", "r-rag", "rag.db"),
  topK: 5,
  minScore: 0.50,
  tokenBudget: 2000,
  enabled: true,
};

function loadConfig() {
  try {
    if (fs.existsSync(CONFIG_PATH)) {
      const raw = fs.readFileSync(CONFIG_PATH, "utf8");
      return { ...DEFAULT_CONFIG, ...JSON.parse(raw) };
    }
  } catch (e) {
    console.error("[r-rag] Config load error:", e.message);
  }
  return { ...DEFAULT_CONFIG };
}

// ─────────────────────────────────────────────
// Query runner
// ─────────────────────────────────────────────

/**
 * Run rag-query.py via subprocess and return parsed results.
 * Returns [] on any error — RAG failure should never break the agent.
 */
function runQuery(queryText, config) {
  const queryScript = path.resolve(os.homedir(), "resonantos-rag", "query", "rag-query.py");
  const venvPython = path.resolve(os.homedir(), "resonantos-rag", "venv", "bin", "python3");

  const python = fs.existsSync(venvPython) ? venvPython : "python3";

  if (!fs.existsSync(queryScript)) {
    console.warn("[r-rag] Query script not found:", queryScript);
    return [];
  }

  try {
    const args = [
      python,
      queryScript,
      JSON.stringify(queryText),
      "--json",
      "--config", CONFIG_PATH,
      "--top", String(config.topK),
      "--min-score", String(config.minScore),
    ];

    const output = execSync(args.join(" "), {
      timeout: 10000,
      encoding: "utf8",
      env: { ...process.env },
    });

    return JSON.parse(output);
  } catch (e) {
    console.warn("[r-rag] Query failed (non-fatal):", e.message?.substring(0, 100));
    return [];
  }
}

// ─────────────────────────────────────────────
// Context formatting
// ─────────────────────────────────────────────

/**
 * Format RAG results for context injection.
 * Respects token budget — truncates if needed.
 */
function formatInjection(results, tokenBudget) {
  if (!results || results.length === 0) return null;

  const lines = ["\n── RAG Context (semantic retrieval) ──"];
  let approxTokens = 10;

  for (const r of results) {
    const sourceName = r.source_name || r.source_path || "unknown";
    const layer = r.doc_layer || "?";
    const chunkIdx = r.chunk_index != null ? r.chunk_index : "?";
    const score = typeof r.score === "number" ? r.score.toFixed(4) : "?";
    const body = r.chunk_text || "";

    const header = `[${sourceName} · ${layer} · chunk ${chunkIdx} · score ${score}]`;
    const chunkTokens = Math.ceil((header.length + body.length) / 4);

    if (approxTokens + chunkTokens > tokenBudget) break;

    lines.push(header);
    lines.push(body);
    lines.push("");
    approxTokens += chunkTokens;
  }

  lines.push("──────────────────────────────────────");
  return lines.join("\n");
}

// ─────────────────────────────────────────────
// OpenClaw extension entry point
// ─────────────────────────────────────────────

module.exports = function rRagExtension(api) {
  let initialized = false;
  let config = { ...DEFAULT_CONFIG };

  function init() {
    if (initialized) return;
    initialized = true;
    config = loadConfig();
    console.log("[r-rag] R-RAG v0.2.0 init", {
      enabled: config.enabled,
      db: config.dbPath,
      topK: config.topK,
      minScore: config.minScore,
      tokenBudget: config.tokenBudget,
    });
  }

  api.on("before_agent_start", async (event, ctx) => {
    try {
      init();
      if (!config.enabled) return;

      const prompt = event.prompt || "";
      if (!prompt || prompt.trim().length < 5) return;

      const systemPrompt = event.systemPrompt || "";

      const results = runQuery(prompt, config);
      if (!results || results.length === 0) return;

      const injection = formatInjection(results, config.tokenBudget);
      if (!injection) return;

      console.log(`[r-rag] Injected ${results.length} chunks (query: "${prompt.substring(0, 50)}...")`);
      return { systemPrompt: systemPrompt + injection };
    } catch (e) {
      // RAG failures are non-fatal — agent continues without RAG context
      console.warn("[r-rag] Extension error (non-fatal):", e.message);
    }
  });
};
