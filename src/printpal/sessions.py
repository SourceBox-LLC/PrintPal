"""Session save/load for PrintPal, backed by SQLite.

Sessions are stored in ``~/.printpal/printpal.db`` and contain the full agent
memory (system prompt + all steps) plus metadata.

Only the fields needed for agent continuation are reconstructed on load;
``model_input_messages`` is dropped (used only for replay/debugging, not for
the agent's live context window).
"""

from __future__ import annotations

import json
from dataclasses import fields as dataclass_fields
from datetime import datetime
from pathlib import Path
from typing import Any

from smolagents.memory import (
    ActionStep,
    AgentMemory,
    PlanningStep,
    TaskStep,
    ToolCall,
)
from smolagents.monitoring import Timing, TokenUsage
from smolagents.utils import AgentError

from . import db

SESSIONS_DIR = Path.home() / ".printpal" / "sessions"  # kept for JSON migration only


def _init_fields_only(cls, data: dict) -> dict:
    """Filter a dict to only the init=True fields of a dataclass."""
    init_names = {f.name for f in dataclass_fields(cls) if f.init}
    return {k: v for k, v in data.items() if k in init_names}


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def next_default_name() -> str:
    """Generate the next auto session name like ``session-2026-07-16-001``."""
    today = datetime.now().strftime("%Y-%m-%d")
    prefix = f"session-{today}-"
    sessions = db.list_all_sessions()
    max_num = 0
    for s in sessions:
        stem = s["name"]
        if stem.startswith(prefix):
            suffix = stem[len(prefix) :]
            if suffix.isdigit():
                max_num = max(max_num, int(suffix))
    return f"{prefix}{max_num + 1:03d}"


def save_session(
    agent: Any,
    name: str,
    model_id: str,
    prompt_history: list[str] | None = None,
    permissions: str = "{}",
) -> int:
    """Save the agent's memory + metadata + prompt history + permissions to the database.

    Returns the row ID. Overwrites if the session already exists — caller
    should confirm first.
    """
    db.init_db()
    memory: AgentMemory = agent.memory
    steps_serialized = memory.get_full_steps()

    created_at = _now_iso()
    existing = db.get_session_by_name(name)
    if existing:
        created_at = existing["created_at"]

    memory_payload = {
        "system_prompt": memory.system_prompt.system_prompt,
        "steps": steps_serialized,
    }

    history_json = json.dumps(prompt_history or [])

    return db.upsert_session(
        name=name,
        created_at=created_at,
        updated_at=_now_iso(),
        step_count=len(memory.steps),
        model_id=model_id,
        memory=memory_payload,
        prompt_history=history_json,
        permissions=permissions,
    )


class _SilentLogger:
    """No-op logger for reconstructing AgentError without printing."""

    def log_error(self, *args, **kwargs):
        pass


def _infer_step_type(step_dict: dict[str, Any]) -> str:
    """Infer the step type from the dict's keys."""
    if "task" in step_dict:
        return "TaskStep"
    if "plan" in step_dict:
        return "PlanningStep"
    if "step_number" in step_dict:
        return "ActionStep"
    return ""


def _reconstruct_step(step_dict: dict[str, Any]) -> Any:
    """Reconstruct a MemoryStep dataclass from its dict form.

    Drops model_input_messages (not needed for continuation).
    """
    step_type = step_dict.get("step_type") or _infer_step_type(step_dict)

    if step_type == "TaskStep":
        return TaskStep(
            task=step_dict["task"],
            task_images=None,
        )

    if step_type == "PlanningStep":
        timing = Timing(**_init_fields_only(Timing, step_dict.get("timing", {})))
        token_usage = (
            TokenUsage(**_init_fields_only(TokenUsage, step_dict["token_usage"]))
            if step_dict.get("token_usage")
            else None
        )
        return PlanningStep(
            model_input_messages=None,
            model_output_message=None,
            plan=step_dict.get("plan", ""),
            timing=timing,
            token_usage=token_usage,
        )

    if step_type == "ActionStep":
        timing = Timing(**_init_fields_only(Timing, step_dict.get("timing", {})))
        token_usage = (
            TokenUsage(**_init_fields_only(TokenUsage, step_dict["token_usage"]))
            if step_dict.get("token_usage")
            else None
        )
        tool_calls = None
        if step_dict.get("tool_calls"):
            tool_calls = [
                ToolCall(
                    name=tc["function"]["name"],
                    arguments=tc["function"]["arguments"],
                    id=tc["id"],
                )
                for tc in step_dict["tool_calls"]
            ]
        error = None
        if step_dict.get("error"):
            err_dict = step_dict["error"]
            error = AgentError(err_dict.get("message", ""), logger=_SilentLogger())
        return ActionStep(
            step_number=step_dict["step_number"],
            timing=timing,
            model_input_messages=None,
            tool_calls=tool_calls,
            error=error,
            model_output_message=None,
            model_output=step_dict.get("model_output"),
            code_action=step_dict.get("code_action"),
            observations=step_dict.get("observations"),
            observations_images=None,
            action_output=step_dict.get("action_output"),
            token_usage=token_usage,
            is_final_answer=step_dict.get("is_final_answer", False),
        )

    return None


def _resolve_name(name_or_id: str) -> str | None:
    """Resolve a name or numeric ID to a session name.

    If ``name_or_id`` is a positive integer string, treat it as the database
    row ID. Otherwise treat it as a session name.
    """
    if name_or_id.isdigit():
        session_id = int(name_or_id)
        row = db.get_session_by_id(session_id)
        return row["name"] if row else None

    row = db.get_session_by_name(name_or_id)
    return row["name"] if row else None


def load_session(agent: Any, name_or_id: str) -> dict | None:
    """Load a session into the agent's memory.

    Returns ``{"success": bool, "prompt_history": list[str], "permissions": str}``
    on completion, or ``None`` if the session could not be resolved.

    ``name_or_id`` can be a session name or a numeric database ID.
    """
    db.init_db()

    name = _resolve_name(name_or_id)
    if name is None:
        print(f"No session '{name_or_id}'. Use /sessions to list available sessions.")
        return None

    row = db.get_session_by_name(name)
    if row is None:
        print(f"No session named '{name}'.")
        return None

    try:
        memory_data = json.loads(row["memory"])
    except json.JSONDecodeError:
        print(f"Session '{name}' is corrupt and can't be loaded.")
        return None

    # Parse prompt history (default to empty list for older sessions)
    prompt_history: list[str] = []
    try:
        prompt_history = json.loads(row.get("prompt_history", "[]"))
    except (json.JSONDecodeError, TypeError):
        pass

    # Parse permissions (default to empty dict for older sessions)
    permissions_json: str = "{}"
    try:
        permissions_json = row.get("permissions", "{}") or "{}"
    except (TypeError, KeyError):
        pass

    try:
        system_prompt = memory_data["system_prompt"]
        steps_raw = memory_data["steps"]

        memory: AgentMemory = agent.memory
        memory.system_prompt.system_prompt = system_prompt
        memory.steps = []
        for step_dict in steps_raw:
            step = _reconstruct_step(step_dict)
            if step is not None:
                memory.steps.append(step)
        return {
            "success": True,
            "prompt_history": prompt_history,
            "permissions": permissions_json,
        }
    except (KeyError, TypeError, ValueError) as e:
        print(f"Session '{name}' is malformed: {e}")
        return {"success": False, "prompt_history": [], "permissions": "{}"}


def list_sessions() -> list[dict[str, Any]]:
    """Return metadata for all sessions, most recent first."""
    db.init_db()
    rows = db.list_all_sessions()
    sessions = []
    for row in rows:
        sessions.append(
            {
                "id": row["id"],
                "name": row["name"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "step_count": row["step_count"],
                "model_id": row["model_id"],
            }
        )
    return sessions


def migrate_json_sessions() -> int:
    """Migrate any existing JSON session files to SQLite. Returns count migrated."""
    db.init_db()
    if not SESSIONS_DIR.exists():
        return 0

    count = 0
    for path in SESSIONS_DIR.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            meta = payload.get("metadata", {})
            memory = payload.get("memory", {})
            name = meta.get("name", path.stem)

            if db.get_session_by_name(name):
                continue

            db.upsert_session(
                name=name,
                created_at=meta.get("created_at", _now_iso()),
                updated_at=meta.get("updated_at", _now_iso()),
                step_count=meta.get("step_count", 0),
                model_id=meta.get("model_id", ""),
                memory=memory,
            )
            count += 1
        except (json.JSONDecodeError, KeyError):
            continue

    if count > 0:
        print(f"Migrated {count} session(s) from JSON to SQLite.")

    return count
