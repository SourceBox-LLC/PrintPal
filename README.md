<div align="center">

# 🖨️ PrintPal

**AI-powered 3D printing assistant — search, slice, and print from your terminal.**

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)](https://python.org)
[![uv](https://img.shields.io/badge/uv-built-blue?logo=uv)](https://docs.astral.sh/uv/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

</div>

---

## What is PrintPal?

PrintPal is a terminal-based 3D printing assistant. You type what you want to print in plain English, and an AI agent handles the rest — searching [Thingiverse](https://www.thingiverse.com), downloading models, slicing them with CuraEngine, and sending them to your [OctoPrint](https://octoprint.org) server.

It's like having a 3D printing expert sitting next to you, ready to find and prepare prints without you ever touching a slicer.

### The pipeline

```
🗣️  You: "find and download a benchy"
         ↓
🔍  Agent searches Thingiverse
         ↓
📥  Downloads the STL (stored in the database)
         ↓
🔪  You: /slice 1                    ← instant, no AI tokens spent
         ↓
🖨️  You: /print 2                    ← preheats, uploads, starts
```

## ✨ Features

- **Natural language search** — just describe what you want to print
- **Self-contained storage** — all models and G-code stored as BLOBs in SQLite, no external files
- **Direct slicing** — `/slice <id>` runs CuraEngine instantly, zero AI tokens
- **Full print pipeline** — `/print <id>` preheats, uploads to OctoPrint, and starts
- **Permission system** — control what the agent can do (Manual / Auto / Bypass modes)
- **Session management** — save/load conversations with full memory and prompt history
- **Live monitoring** — `/print status` shows real-time temps and job progress
- **Cost tracking** — `/cost` shows token usage and estimated dollar cost
- **Print queue** — queue prints when the printer is busy
- **DB backups** — `/backup` snapshots your entire database
- **Settings management** — `/config` to view and set OctoPrint URL, API keys, etc.

## 🚀 Quick start

### Prerequisites

- **Python 3.10+**
- **[uv](https://docs.astral.sh/uv/)** — dependency manager
- **[Ultimaker Cura](https://ultimaker.com/software/ultimaker-cura/)** — for slicing (auto-detected)
- **An OctoPrint server** — for printing (optional, only needed for Level 3)
- **An Anthropic API key** — for the AI agent (Claude Sonnet)

### Setup

```bash
# Clone the repo
git clone <repo-url>
cd PrintPal

# Copy the example config and add your keys
cp .env.example .env
# Edit .env — add your ANTHROPIC_API_KEY and THINGIVERSE_TOKEN

# Run it!
uv run printpal
```

You'll see the PrintPal banner with a random tip:

```
┌───────────────────────────────── PrintPal ──────────────────────────────────┐
│ PrintMCP: connected (14 tools)                                              │
│ model: claude-sonnet-4-6                                                    │
│ tip: Type a natural language request like 'find and download a benchy'...   │
└─────────────────────────────────────────────────────────────────────────────┘
PrintPal  no things  model: claude-sonnet-4-6  mcp: 14 tools  mode: manual
> find and download a benchy
```

### Configuration

Settings can be stored in `.env` (for initial setup) or managed at runtime with `/config` (stored in the database, overrides `.env`):

```bash
# Inside PrintPal:
/config set octoprint_url http://192.168.1.50
/config set octoprint_api_key your-api-key-here
/config set thingiverse_token your-thingiverse-token
/config set auto_save true          # auto-save sessions after each prompt
```

| Setting | Environment variable | Required for | Masked? |
|---------|---------------------|-------------|---------|
| `thingiverse_token` | `THINGIVERSE_TOKEN` | Searching & downloading | Yes |
| `octoprint_url` | `OCTOPRINT_URL` | Printing | No |
| `octoprint_api_key` | `OCTOPRINT_API_KEY` | Printing | Yes |
| `cura_dir` | `PRINTMCP_CURA_DIR` | Slicing (auto-detected) | No |
| `auto_save` | — | Optional convenience | No |

## 🎮 Commands

### Session management

| Command | Description |
|---------|-------------|
| `/save [name]` | Save the current session (auto-names if no name given) |
| `/load <name\|id>` | Load a saved session by name or numeric ID |
| `/sessions` | List all saved sessions |
| `/new` | Clear the session and start fresh (alias: `/clear`) |
| `/cost` | Show token usage and estimated cost for this session |
| `/exit` | Exit PrintPal (aliases: `/quit`, `/q`) |

### Things (downloaded models & G-code)

| Command | Description |
|---------|-------------|
| `/thing` | List all things in the database |
| `/thing <id>` | Show details for a specific thing |
| `/thing export <id> [dest]` | Write a thing's file back to disk |
| `/thing delete <id>` | Remove a thing from the database |

### Slicing

| Command | Description |
|---------|-------------|
| `/slice <id>` | Slice a model to G-code using CuraEngine |
| `/slice <id> --layer-height 0.12` | Set layer height (0.05–0.6mm) |
| `/slice <id> --infill 40 --supports` | Set infill % and enable supports |
| `/slice <id> --printer creality_ender3pro` | Set printer profile |
| `/slice <id> --temp 210 --bed 65` | Set nozzle and bed temperatures |
| `/slice <id> --adhesion brim` | Set adhesion type (skirt/brim/raft/none) |

Short flags: `--lh`, `--inf`, `--sup`, `--ad`, `--t`, `--b`, `--p`

### Printing

| Command | Description |
|---------|-------------|
| `/print <id>` | Full pipeline: check → connect → preheat → upload → start |
| `/print <id> --no-preheat` | Skip preheating, let G-code handle temps |
| `/print status` | Live auto-refreshing printer status (Ctrl+C to stop) |
| `/print pause` | Pause the active print |
| `/print resume` | Resume the paused print |
| `/print cancel` | Cancel the print (G-code is kept for reprinting) |
| `/print connect` | Connect to the printer |
| `/print disconnect` | Disconnect from the printer |
| `/print files` | List G-code files on the OctoPrint server |
| `/print queue` | Show the print queue |
| `/print queue remove <pos>` | Remove an item from the queue |
| `/print queue clear` | Clear the entire queue |

### Permissions

| Command | Description |
|---------|-------------|
| `/mode` | Show current mode and tool categories |
| `/mode default` | Manual — ask for every tool call |
| `/mode auto` | Auto — approve searches/downloads, ask before physical actions |
| `/mode bypass` | Bypass — approve everything (with warning) |

**Shift+Tab** cycles between Manual and Auto modes.

When the agent calls a tool, you'll see:
```
┌─ Permission Required ──────────────────────────┐
│ Tool:     thingiverse_search_models            │
│ Category: Read-only                            │
│ [y] Yes  [n] No  [a] Always allow this tool  │
└────────────────────────────────────────────────┘
```

### App management

| Command | Description |
|---------|-------------|
| `/config` | Show all settings (API keys masked) |
| `/config set <key> <value>` | Set a setting |
| `/config get <key>` | Show one setting (unmasked) |
| `/config unset <key>` | Delete a setting |
| `/logs` | Show recent logs (last 20) |
| `/logs 50` | Show last N logs |
| `/logs error` | Show only errors |
| `/logs clear` | Clear all logs |
| `/backup` | Create a database backup |
| `/backup list` | List backups |
| `/backup restore <name>` | Restore from a backup |
| `/redraw` | Clear and redraw the UI (use after terminal resize) |
| `/self-destruct` | Delete ALL data — database, backups, everything. Irreversible. |
| `/help` | Show all available commands |

## 🏗️ Architecture

```
src/printpal/
├── __init__.py              # Package marker
├── __main__.py              # python -m printpal entry point
├── app.py                   # Main REPL loop, bootstrap, command dispatch
├── config.py                # MODEL_ID, settings mapping, tips, examples
├── ui.py                    # Shared console, accent color, format helpers, progress bars
├── db.py                    # SQLite layer (sessions, things, queue, settings, logs, backups)
├── sessions.py              # Session save/load (agent memory + prompt history)
├── permissions.py           # Permission system (ApprovalMode, PermissionTool wrapper)
├── scanner.py               # Download + slice scanner (captures files into BLOBs)
├── completer.py             # Command autocomplete (prefix matching)
├── pricing.py               # Model pricing data for /cost
└── commands/                # All /slash command implementations
    ├── __init__.py           # Re-exports all cmd_* functions + COMMANDS dict
    ├── helpers.py            # Shared utilities (tool lookup, slice flags, preheat)
    ├── session.py            # /save, /load, /sessions
    ├── thing.py              # /thing, /slice
    ├── print.py              # /print and all sub-commands
    ├── mode.py               # /mode
    ├── admin.py              # /config, /cost, /logs, /backup
    └── help.py               # /help
```

PrintPal connects to **[PrintMCP](https://github.com/SourceBox-LLC/PrintMCP)** — an MCP server that provides the 3D printing tools:

- **Level 1 (Thingiverse)** — search, inspect, download 3D models
- **Level 2 (Cura)** — slice models into G-code via CuraEngine
- **Level 3 (OctoPrint)** — upload, print, monitor, control

The AI agent (powered by [smolagents](https://github.com/huggingface/smolagents) + LiteLLM) uses these tools autonomously. Slash commands like `/slice` and `/print` call the tools directly — no AI tokens spent.

### Database

Everything is stored in a single SQLite file at `~/.printpal/printpal.db`:

| Table | What it stores |
|-------|---------------|
| `sessions` | Agent memory, prompt history, permissions per session |
| `things` | Downloaded models and sliced G-code (as BLOBs) |
| `print_queue` | Queued print jobs |
| `settings` | App configuration (OctoPrint URL, API keys, etc.) |
| `logs` | Error and info logs |
| `scanned_steps` | Tracks which agent steps have been processed for downloads |

Backups are stored at `~/.printpal/backups/`.

## 🔧 Troubleshooting

| Problem | Solution |
|---------|----------|
| `MCP server didn't respond in time` | Ensure `uvx printmcp` works: run `uvx printmcp --version` |
| `THINGIVERSE_TOKEN is not set` | Run `/config set thingiverse_token <token>` or add to `.env` |
| `OCTOPRINT_URL and OCTOPRINT_API_KEY not set` | Run `/config set octoprint_url <url>` and `/config set octoprint_api_key <key>` |
| `CuraEngine not found` | Install Ultimaker Cura, or set `PRINTMCP_CURA_DIR` via `/config set cura_dir <path>` |
| Permission denied on every tool call | Switch to auto mode: `/mode auto` or press Shift+Tab |
| `uv` not found | Install uv: `pip install uv` or see [uv docs](https://docs.astral.sh/uv/) |

## 📋 Requirements

- **Python ≥ 3.10**
- **[uv](https://docs.astral.sh/uv/)** for dependency management
- **[PrintMCP](https://pypi.org/project/printmcp/)** — installed automatically via `uvx`
- **[Ultimaker Cura](https://ultimaker.com/software/ultimaker-cura/)** — for slicing (Level 2)
- **[OctoPrint](https://octoprint.org/)** server — for printing (Level 3)
- **Anthropic API key** — for the AI agent (Claude Sonnet)

## 📄 License

Licensed under the **[MIT License](LICENSE)** — © 2026 SourceBox LLC.

You may freely use, modify, and distribute this software, provided you retain
the copyright and license notice.

---

<div align="center">

Built with [smolagents](https://github.com/huggingface/smolagents), [PrintMCP](https://github.com/SourceBox-LLC/PrintMCP), [Rich](https://github.com/Textualize/rich), and [prompt_toolkit](https://github.com/prompt-toolkit/python-prompt-toolkit).

</div>