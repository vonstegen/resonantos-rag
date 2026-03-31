#!/usr/bin/env node
/**
 * install.js — ResonantOS RAG Layer 4 Installer
 *
 * Mirrors the install.js pattern from resonantos-alpha.
 * Run: node ~/resonantos-rag/install.js
 */

import { execSync, spawnSync } from "child_process";
import { existsSync, mkdirSync, copyFileSync, writeFileSync, readFileSync } from "fs";
import { join, resolve } from "path";
import { homedir } from "os";

const HOME = homedir();
const RAG_DIR = resolve(import.meta.dirname || process.cwd());
const WORKSPACE = join(HOME, ".openclaw", "workspace");
const RAG_WORKSPACE = join(WORKSPACE, "r-rag");
const EXTENSIONS_DIR = join(HOME, ".openclaw", "agents", "main", "agent", "extensions");
const OPENCLAW_CONFIG = join(HOME, ".openclaw", "openclaw.json");

const green = (s) => `\x1b[32m${s}\x1b[0m`;
const red = (s) => `\x1b[31m${s}\x1b[0m`;
const yellow = (s) => `\x1b[33m${s}\x1b[0m`;
const bold = (s) => `\x1b[1m${s}\x1b[0m`;

function log(msg) { console.log(`  ${msg}`); }
function ok(msg) { console.log(`  ${green("✓")} ${msg}`); }
function warn(msg) { console.log(`  ${yellow("⚠")} ${msg}`); }
function err(msg) { console.log(`  ${red("✗")} ${msg}`); }
function step(msg) { console.log(`\n${bold(msg)}`); }

function run(cmd, opts = {}) {
  try {
    return execSync(cmd, { encoding: "utf8", stdio: "pipe", ...opts });
  } catch (e) {
    return null;
  }
}

function runRequired(cmd, failMsg) {
  const result = run(cmd);
  if (result === null) {
    err(failMsg);
    process.exit(1);
  }
  return result;
}

// ─────────────────────────────────────────────
// Step 1: Check dependencies
// ─────────────────────────────────────────────

step("1. Checking dependencies");

// Node
const nodeVersion = run("node --version")?.trim();
if (!nodeVersion) {
  err("Node.js not found");
  process.exit(1);
}
const nodeMajor = parseInt(nodeVersion.replace("v", "").split(".")[0]);
if (nodeMajor < 18) {
  err(`Node.js 18+ required (found ${nodeVersion})`);
  process.exit(1);
}
ok(`Node.js ${nodeVersion}`);

// Python3
const pythonCmd = run("python3 --version") ? "python3" : run("python --version") ? "python" : null;
if (!pythonCmd) {
  err("Python 3 not found");
  process.exit(1);
}
ok(`Python (${pythonCmd})`);

// pip
const pipCmd = run("pip3 --version") ? "pip3" : run("pip --version") ? "pip" : null;
if (!pipCmd) {
  err("pip not found. Run: sudo apt install python3-pip");
  process.exit(1);
}
ok("pip");

// Ollama
const ollamaVersion = run("ollama --version")?.trim();
if (!ollamaVersion) {
  err("Ollama not found. Install from: https://ollama.com");
  process.exit(1);
}
ok(`Ollama (${ollamaVersion})`);

// nomic-embed-text
const ollamaList = run("ollama list") || "";
if (!ollamaList.includes("nomic-embed-text")) {
  warn("nomic-embed-text not found — pulling now...");
  const pull = spawnSync("ollama", ["pull", "nomic-embed-text"], { stdio: "inherit" });
  if (pull.status !== 0) {
    err("Failed to pull nomic-embed-text");
    process.exit(1);
  }
  ok("nomic-embed-text pulled");
} else {
  ok("nomic-embed-text available");
}

// OpenClaw workspace
if (!existsSync(WORKSPACE)) {
  err(`OpenClaw workspace not found at ${WORKSPACE}`);
  err("Is ResonantOS installed? Run: node ~/resonantos-alpha/install.js");
  process.exit(1);
}
ok("OpenClaw workspace found");

// ─────────────────────────────────────────────
// Step 2: Create workspace directories
// ─────────────────────────────────────────────

step("2. Setting up workspace");

mkdirSync(RAG_WORKSPACE, { recursive: true });
ok(`r-rag workspace: ${RAG_WORKSPACE}`);

// ─────────────────────────────────────────────
// Step 3: Install Python dependencies
// ─────────────────────────────────────────────

step("3. Installing Python dependencies");

const venvPath = join(RAG_DIR, "venv");
if (!existsSync(venvPath)) {
  log("Creating Python venv...");
  runRequired(`${pythonCmd} -m venv "${venvPath}"`, "Failed to create venv");
}
ok("Python venv ready");

const pipBin = join(venvPath, "bin", "pip");
runRequired(`"${pipBin}" install -q -r "${join(RAG_DIR, "indexer", "requirements.txt")}"`,
  "Failed to install Python dependencies");
ok("Python dependencies installed");

// ─────────────────────────────────────────────
// Step 4: Deploy config (skip if exists)
// ─────────────────────────────────────────────

step("4. Writing configuration");

const configDest = join(RAG_WORKSPACE, "config.json");
if (!existsSync(configDest)) {
  copyFileSync(join(RAG_DIR, "config", "rag-config.json"), configDest);
  ok(`Config written: ${configDest}`);
} else {
  ok("Config already exists — skipping");
}

// ─────────────────────────────────────────────
// Step 5: Install OpenClaw extension
// ─────────────────────────────────────────────

step("5. Installing OpenClaw extension");

if (!existsSync(EXTENSIONS_DIR)) {
  mkdirSync(EXTENSIONS_DIR, { recursive: true });
}

const extSrc = join(RAG_DIR, "extension", "r-rag.js");
const extDest = join(EXTENSIONS_DIR, "r-rag.js");

if (!existsSync(extDest)) {
  copyFileSync(extSrc, extDest);
  ok(`Extension installed: ${extDest}`);
} else {
  ok("Extension already exists — skipping");
}

// ─────────────────────────────────────────────
// Step 6: Run initial index
// ─────────────────────────────────────────────

step("6. Running initial SSoT index");

const pythonBin = join(venvPath, "bin", "python3");
const indexerScript = join(RAG_DIR, "indexer", "rag-indexer.py");
const configPath = configDest;

log("Indexing SSoT documents...");
const indexResult = spawnSync(pythonBin, [indexerScript, "--config", configPath], {
  stdio: "inherit",
  cwd: RAG_DIR,
});

if (indexResult.status !== 0) {
  warn("Initial index failed — you can run it manually:");
  warn(`  python3 ${indexerScript}`);
} else {
  ok("Initial index complete");
}

// ─────────────────────────────────────────────
// Done
// ─────────────────────────────────────────────

console.log(`
${bold("═══════════════════════════════════════════")}
${bold("  ResonantOS RAG Layer 4 — Installed")}
${bold("═══════════════════════════════════════════")}

  Your 4-layer memory stack is now complete:

    Layer 1  MEMORY.md           ✓
    Layer 2  R-Awareness headers  ✓
    Layer 3  LCM compression      ✓
    Layer 4  RAG semantic search  ${green("✓  NEW")}

  Next steps:

    Restart OpenClaw gateway to load the r-rag extension:
    ${bold("openclaw gateway restart")}

    Test semantic search:
    ${bold(`python3 ${join(RAG_DIR, "query", "rag-query.py")} "your query here"`)}

    Re-index after updating SSoT docs:
    ${bold(`python3 ${join(RAG_DIR, "indexer", "rag-indexer.py")}`)}

    Run tests:
    ${bold(`python3 ${join(RAG_DIR, "tests", "test-query.py")}`)}

  Config: ${configDest}
  Docs:   https://github.com/vonstegen/resonantos-rag
`);
