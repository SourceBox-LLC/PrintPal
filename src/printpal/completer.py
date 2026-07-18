"""Command autocomplete for PrintPal's prompt.

Provides a prefix-matching completer for slash commands. Only activates
when input starts with ``/`` — natural language prompts are not completed.
"""

from __future__ import annotations

from prompt_toolkit.completion import Completer, Completion

# Command completion tree.
# Aliases (/quit, /q, /clear) are excluded — only canonical commands shown.
COMMAND_COMPLETION = {
    "/save": None,
    "/load": None,
    "/sessions": None,
    "/thing": {"delete": None, "export": None},
    "/slice": None,
    "/print": {
        "status": None,
        "pause": None,
        "resume": None,
        "cancel": None,
        "connect": None,
        "disconnect": None,
        "files": None,
        "queue": {"remove": None, "clear": None},
    },
    "/mode": {"default": None, "auto": None, "bypass": None},
    "/config": {"set": None, "get": None, "unset": None},
    "/cost": None,
    "/logs": {"error": None, "clear": None},
    "/backup": {"list": None, "restore": None},
    "/redraw": None,
    "/self-destruct": None,
    "/new": None,
    "/exit": None,
    "/help": None,
}


class CommandCompleter(Completer):
    """Prefix-matching completer for slash commands.

    Shows all commands starting with the typed prefix (e.g. /s -> /save,
    /sessions, /slice). Also completes sub-commands (e.g. /print q -> queue).
    Only activates when input starts with /.
    """

    def __init__(self, tree: dict | None = None):
        self.tree = tree if tree is not None else COMMAND_COMPLETION

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor

        if not text.startswith("/"):
            return

        words = text.split()
        ends_with_space = text.endswith(" ")

        if not ends_with_space and len(words) <= 1:
            partial = words[0] if words else "/"
            for cmd in sorted(self.tree.keys()):
                if cmd.startswith(partial):
                    yield Completion(cmd, start_position=-len(partial))
        else:
            cmd = words[0]
            subtree = self.tree.get(cmd)
            if not isinstance(subtree, dict):
                return
            partial = words[-1] if not ends_with_space else ""
            for sub in sorted(subtree.keys()):
                if sub.startswith(partial):
                    yield Completion(sub, start_position=-len(partial))
