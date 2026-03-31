/**
 * r-rag.js — ResonantOS RAG Extension for OpenClaw
 *
 * Hooks into the OpenClaw extension pipeline to inject semantically
 * relevant SSoT chunks into the agent's context window.
 *
 * Runs AFTER r-awareness.js — enriches keyword-triggered doc loading
 * with precise semantic chunk injection.
 *
 * Install location: ~/.openclaw/agents/main/agent/extensions/r-rag.js
 */

import { execSync } from "child_process";
import { existsSync, readFileSync } from "fs";
import { join, resolve } from "path";
import { homedir } from "os";

// ─────────────────────────────────────────────
// Config
// ─────────────────────────────────────────────

const CONFIG_PATH = join(homedir(), ".openclaw", "workspace", "r-rag", "config.json");
const DEFAULT_CONFIG = {
  ollamaUrl: "http://localhost:11434",
  embeddingModel: "nomic-embed-text",
  dbPath: join(homedir(), ".openclaw", "workspace", "r-rag", "rag.db"),
  topK: 5,
  minScore: 0.65,
  tokenBudget: 2000,   // max tokens RAG may consume from the context budget
  enabled: true,
};

function loadConfig() {
  try {
    if (existsSync(CONFIG_PATH)) {
      const raw = readFileSync(CONFIG_PATH, "utf8");
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
  const queryScript = resolve(homedir(), "resonantos-rag", "query", "rag-query.py");
  const venvPython = resolve(homedir(), "resonantos-rag", "venv", "bin", "python3");

  // Fall back to system python3 if venv not found
  const python = existsSync(venvPython) ? venvPython : "python3";

  if (!existsSync(queryScript)) {
    console.warn("[r-rag] Query script not found:", queryScript);
    return [];
  }

  try {
    const args = [
      python,
      queryScript,
      JSON.stringify(queryText),
      "--json",
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

  const lines = ["── RAG Context (semantic retrieval) ──"];
  let approxTokens = 10; // header

  for (const r of results) {
    const header = `[${r.source_name} · ${r.doc_layer} · chunk ${r.chunk_index} · score ${r.score}]`;
    const body = r.chunk_text;
    const chunkTokens = Math.ceil((header.length + body.length) / 4); // rough estimate

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
// OpenClaw extension hook
// ─────────────────────────────────────────────

/**
 * Main extension hook — called by OpenClaw on each agent turn.
 *
 * @param {object} ctx - Extension context provided by OpenClaw
 *   ctx.message      - Current user message
 *   ctx.injectBefore - Function to inject text before system prompt
 *   ctx.injectAfter  - Function to inject text after system prompt
 *   ctx.session      - Current session info
 */
export async function onTurn(ctx) {
  const config = loadConfig();

  if (!config.enabled) return;

  const message = ctx?.message?.text || ctx?.message || "";
  if (!message || message.trim().length < 5) return;

  try {
    const results = runQuery(message, config);

    if (!results || results.length === 0) return;

    const injection = formatInjection(results, config.tokenBudget);
    if (!injection) return;

    // Inject after system prompt, before conversation history
    if (typeof ctx.injectAfter === "function") {
      ctx.injectAfter(injection);
    }

    console.log(`[r-rag] Injected ${results.length} chunks (query: "${message.substring(0, 50)}...")`);
  } catch (e) {
    // RAG failures are non-fatal — agent continues without RAG context
    console.warn("[r-rag] Extension error (non-fatal):", e.message);
  }
}

/**
 * Extension metadata — used by OpenClaw's extension registry.
 */
export const meta = {
  name: "r-rag",
  version: "0.1.0",
  description: "ResonantOS RAG Layer 4 — semantic SSoT chunk injection",
  author: "vonstegen",
  runsAfter: ["r-awareness"],
};
