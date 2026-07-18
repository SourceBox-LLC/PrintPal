"""Application-level configuration for PrintPal.

This module holds constants that are shared across the app: the active model
ID, environment variable mappings, tips, and example prompts. When model
switching is added, the ``MODEL_ID`` and model registry will live here.
"""

# The active LLM model ID (LiteLLM format).
# When model switching is added, this will be read from DB settings.
MODEL_ID = "claude-sonnet-4-6"

# Settings keys that map to environment variables for PrintMCP.
# DB settings override .env values — injected into os.environ on startup.
SETTING_TO_ENV = {
    "octoprint_url": "OCTOPRINT_URL",
    "octoprint_api_key": "OCTOPRINT_API_KEY",
    "thingiverse_token": "THINGIVERSE_TOKEN",
    "cura_dir": "PRINTMCP_CURA_DIR",
}

TIPS = [
    "Type a natural language request like 'find and download a benchy' to let the agent search Thingiverse for you.",
    "Use /slice <id> to slice a downloaded model — no tokens spent, instant CuraEngine slicing.",
    "Use /thing <id> to see full details about a downloaded or sliced file.",
    "Use /thing export <id> to write a file from the database back to disk.",
    "Use /print <id> to run the full print pipeline: preheat, upload, and start on OctoPrint.",
    "Use /print status for a live auto-refreshing view of your printer's temps and job progress.",
    "Use /save to persist your session — agent memory and prompt history are stored and can be resumed later with /load.",
    "Use /sessions to list saved sessions and /load <id> to resume by number.",
    "Use /print queue to manage items when the printer is busy — prints won't auto-start, you decide when to begin.",
    "Use /slice 1 --layer-height 0.12 --supports for finer prints with support material.",
    "Use /print cancel to abort a print — the G-code is kept so you can reprint later.",
    "All files are stored in the database as BLOBs — the database file is fully portable.",
    "Use /print <id> --no-preheat to skip preheating if you want the G-code to handle temps itself.",
    "Use /thing delete <id> to remove a file from the database — no disk cleanup needed.",
    "The agent sees tool output schemas up front, so it calls tools correctly on the first try.",
    "Use /print connect or /print disconnect to manage the printer's serial connection manually.",
    "Use /print files to list G-code files already on your OctoPrint server.",
    "Up arrow recalls previous prompts from the current session's history.",
    "Use /mode auto to auto-approve searches and downloads — the agent only asks before physical printer actions.",
    "Press Shift+Tab to cycle between Manual and Auto permission modes.",
    "Use /config to view and set app settings like OctoPrint URL and Thingiverse token.",
    "Use /cost to see token usage and estimated cost for the current session.",
    "Use /logs to view recent error and info logs.",
    "Use /backup to create a snapshot of your entire database.",
    "Resized your terminal? Use /redraw to clean up the UI without losing your session.",
]

EXAMPLES = [
    "find and download a benchy",
    "find and download a batman action figure",
    "search for a small articulated dragon",
    "download thing 2852299 from thingiverse",
    "find a phone stand to print",
    "search for a coffee cup model",
    "find and download a small vase under 5MB",
    "search for an articulated octopus",
]
