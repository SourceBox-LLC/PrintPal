"""Permission mode command: /mode."""

from __future__ import annotations

from rich.panel import Panel
from rich.text import Text

from ..permissions import PHYSICAL, READ_ONLY, SAFE_ACTIONS, ApprovalMode
from ..ui import ACCENT, console, prompt_yes_no


def cmd_mode(args: list[str], perm_state) -> None:
    """Show or set the permission mode."""
    if not args:
        current = perm_state.mode
        lines = [
            Text(
                f"Current: \u25cf {current.label} ({current.value})",
                style=f"bold {ACCENT}",
            ),
            Text(""),
            Text("Modes:", style="bold"),
        ]
        for mode in ApprovalMode:
            marker = "\u25cf" if mode == current else "\u25cb"
            warning = " \u26a0" if mode == ApprovalMode.BYPASS else ""
            lines.append(Text(f"  {marker} {mode.value:8s} \u2014 {mode.label}{warning}"))

        lines.append(Text(""))
        lines.append(Text("Tool Categories:", style="bold"))
        lines.append(Text(f"  \U0001f441  Read-only:     {', '.join(sorted(READ_ONLY))}"))
        lines.append(Text(f"  \u2702  Safe actions:  {', '.join(sorted(SAFE_ACTIONS))}"))
        lines.append(Text(f"  \U0001f527  Physical:      {', '.join(sorted(PHYSICAL))}"))

        if perm_state.allow_list:
            lines.append(Text(""))
            lines.append(
                Text(
                    f"Always allowed this session: {', '.join(sorted(perm_state.allow_list))}",
                    style="green",
                )
            )
        console.print(
            Panel(
                Text("\n").join(lines),
                title=Text("Permission Mode", style="bold"),
                border_style=ACCENT,
            )
        )
        return

    mode_str = args[0].lower()
    try:
        new_mode = ApprovalMode(mode_str)
    except ValueError:
        console.print(
            Text(
                f"Unknown mode '{mode_str}'. Available: default, auto, bypass",
                style="bold red",
            )
        )
        return

    if new_mode == ApprovalMode.BYPASS and perm_state.mode != ApprovalMode.BYPASS:
        if not prompt_yes_no(
            "Bypass mode auto-approves ALL tool calls including physical printer actuation.\n"
            "  The agent can start prints, set temperatures, and move axes without asking.\n"
            "  Continue? [y/N] "
        ):
            console.print(Text("Mode unchanged.", style="dim"))
            return

    perm_state.mode = new_mode
    style = (
        "green"
        if new_mode == ApprovalMode.AUTO
        else "bold red"
        if new_mode == ApprovalMode.BYPASS
        else "dim"
    )
    console.print(Text(f"Mode set to {new_mode.label} ({new_mode.value}).", style=f"bold {style}"))
