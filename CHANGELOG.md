# Changelog

All notable changes to PrintPal are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-07-18

### Added

- **AI agent pipeline** — natural language search, download, slice, and print 3D models via Thingiverse, CuraEngine, and OctoPrint
- **24 slash commands** — `/save`, `/load`, `/sessions`, `/thing`, `/slice`, `/print` (with sub-commands), `/mode`, `/config`, `/cost`, `/logs`, `/backup`, `/redraw`, `/self-destruct`, `/help`, `/new`, `/exit`
- **Permission system** — three modes (Manual, Auto, Bypass), per-session allow-list, Shift+Tab cycling, per-tool approval prompts with "always allow"
- **Session management** — save/load with full agent memory, prompt history, and permissions stored in SQLite
- **BLOB storage** — all downloaded models and sliced G-code stored as BLOBs in the database, no external files
- **Download + slice scanner** — automatically captures files from agent tool calls into the database
- **Print queue** — queue prints when the printer is busy, lazy advancement
- **Cost tracking** — `/cost` shows token usage and estimated dollar cost via smolagents Monitor
- **DB settings** — `/config` manages OctoPrint URL, API keys, Thingiverse token, Cura path, auto-save
- **Logging** — DB-stored error and info logs, viewable via `/logs`
- **Backups** — `/backup` creates snapshots of the entire database
- **Self-destruct** — `/self-destruct` permanently deletes all PrintPal data with two-step confirmation
- **Autocomplete** — prefix-matching command completion via prompt_toolkit
- **Prompt history** — up/down arrow recall, persisted per-session in the database
- **Placeholder text** — dim example prompts that vanish on keypress
- **Visual UI** — ASCII art banner, status bar with token usage bar and cost, separator lines, `❯` prompt, `★` tips, `⚠` permission warnings, `●`/`○` mode indicators, category icons
- **Width-aware status bar** — adapts to terminal width, `/redraw` to fix after resize
- **mcpadapt monkeypatch** — workaround for jsonref proxy serialization bug
- **Error resilience** — no unhandled exception crashes the app
- **Graceful Ctrl+C** — interrupt agent runs without losing state
- **Auto-save** — optional, names sessions from first prompt
- **MIT license**
- **README.md** and **AGENTS.md** documentation
- **.env.example** configuration template