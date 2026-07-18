from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

DB_PATH = Path.home() / ".printpal" / "printpal.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    step_count  INTEGER NOT NULL DEFAULT 0,
    model_id    TEXT NOT NULL DEFAULT '',
    memory      TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS things (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    thingiverse_id INTEGER,
    name          TEXT NOT NULL,
    creator       TEXT,
    license       TEXT,
    url           TEXT,
    file_name     TEXT NOT NULL,
    file_size     INTEGER,
    file_data     BLOB,
    file_type     TEXT NOT NULL DEFAULT 'model',
    sliced_from   INTEGER,
    status        TEXT NOT NULL DEFAULT 'downloaded',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scanned_steps (
    step_key TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS print_queue (
    position   INTEGER PRIMARY KEY AUTOINCREMENT,
    thing_id   INTEGER NOT NULL,
    added_at   TEXT NOT NULL,
    FOREIGN KEY (thing_id) REFERENCES things(id)
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    level      TEXT NOT NULL,
    message    TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Create the database and tables if they don't exist."""
    conn = _get_conn()
    try:
        conn.executescript(_SCHEMA)
        conn.commit()

        # Add file_data column if it doesn't exist (for existing DBs)
        columns = [
            row[1] for row in conn.execute("PRAGMA table_info(things)").fetchall()
        ]
        if "file_data" not in columns:
            conn.execute("ALTER TABLE things ADD COLUMN file_data BLOB")
            conn.commit()

        # Add prompt_history column to sessions if it doesn't exist
        sess_cols = [
            row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()
        ]
        if "prompt_history" not in sess_cols:
            conn.execute(
                "ALTER TABLE sessions ADD COLUMN prompt_history TEXT NOT NULL DEFAULT '[]'"
            )
            conn.commit()

        # Add permissions column to sessions if it doesn't exist
        if "permissions" not in sess_cols:
            conn.execute(
                "ALTER TABLE sessions ADD COLUMN permissions TEXT NOT NULL DEFAULT '{}'"
            )
            conn.commit()
    finally:
        conn.close()


def migrate_to_blob_storage() -> int:
    """Migrate old things rows with file_path to BLOB storage.

    For each row that has a file_path but no file_data:
    1. Read the file from disk
    2. Store the bytes in file_data
    3. Delete the file from disk
    4. Drop the file_path column

    Returns the number of files migrated.
    """
    conn = _get_conn()
    try:
        # Check if file_path column exists
        columns = [
            row[1] for row in conn.execute("PRAGMA table_info(things)").fetchall()
        ]
        if "file_path" not in columns:
            return 0

        # Migrate rows with file_path but no file_data
        rows = conn.execute(
            "SELECT id, file_path FROM things WHERE file_path IS NOT NULL AND file_data IS NULL"
        ).fetchall()

        migrated = 0
        for row in rows:
            path = Path(row["file_path"])
            if path.is_file():
                file_bytes = path.read_bytes()
                conn.execute(
                    "UPDATE things SET file_data = ?, file_size = ? WHERE id = ?",
                    (file_bytes, len(file_bytes), row["id"]),
                )
                path.unlink()
                migrated += 1
            else:
                # File missing — still drop the path, keep the row
                conn.execute(
                    "UPDATE things SET file_path = NULL WHERE id = ?",
                    (row["id"],),
                )

        # Also migrate rows that have file_path AND file_data already (just delete disk file)
        rows2 = conn.execute(
            "SELECT id, file_path FROM things WHERE file_path IS NOT NULL AND file_data IS NOT NULL"
        ).fetchall()
        for row in rows2:
            path = Path(row["file_path"])
            if path.is_file():
                path.unlink()

        # Drop the file_path column (SQLite 3.35+)
        conn.execute("ALTER TABLE things DROP COLUMN file_path")
        conn.commit()
        return migrated
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


def upsert_session(
    name: str,
    created_at: str,
    updated_at: str,
    step_count: int,
    model_id: str,
    memory: dict[str, Any],
    prompt_history: str = "[]",
    permissions: str = "{}",
) -> int:
    """Insert or update a session by name. Returns the row ID."""
    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT INTO sessions (name, created_at, updated_at, step_count, model_id, memory, prompt_history, permissions)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                updated_at = excluded.updated_at,
                step_count = excluded.step_count,
                model_id   = excluded.model_id,
                memory     = excluded.memory,
                prompt_history = excluded.prompt_history,
                permissions = excluded.permissions
            """,
            (
                name,
                created_at,
                updated_at,
                step_count,
                model_id,
                json.dumps(memory, default=str),
                prompt_history,
                permissions,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT id FROM sessions WHERE name = ?", (name,)).fetchone()
        return row["id"] if row else 0
    finally:
        conn.close()


def get_session_by_name(name: str) -> dict[str, Any] | None:
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM sessions WHERE name = ?", (name,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_session_by_id(session_id: int) -> dict[str, Any] | None:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_all_sessions() -> list[dict[str, Any]]:
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM sessions ORDER BY updated_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Things
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def insert_thing(
    thingiverse_id: int | None,
    name: str,
    creator: str | None,
    license: str | None,
    url: str | None,
    file_name: str,
    file_size: int | None,
    file_data: bytes | None,
    file_type: str = "model",
    sliced_from: int | None = None,
    status: str = "downloaded",
) -> int:
    """Insert a thing row. Returns the row ID."""
    conn = _get_conn()
    try:
        now = _now_iso()
        conn.execute(
            """
            INSERT INTO things (thingiverse_id, name, creator, license, url,
                                 file_name, file_size, file_data, file_type,
                                 sliced_from, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                thingiverse_id,
                name,
                creator,
                license,
                url,
                file_name,
                file_size,
                file_data,
                file_type,
                sliced_from,
                status,
                now,
                now,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT last_insert_rowid()").fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def get_thing(thing_id: int) -> dict[str, Any] | None:
    """Return a thing row by ID (includes file_data), or None."""
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM things WHERE id = ?", (thing_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_thing_file_data(thing_id: int) -> bytes | None:
    """Return just the file_data BLOB for a thing, or None."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT file_data FROM things WHERE id = ?", (thing_id,)
        ).fetchone()
        return row["file_data"] if row else None
    finally:
        conn.close()


def list_things() -> list[dict[str, Any]]:
    """Return all things (excluding file_data for performance), most recent first."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            """SELECT id, thingiverse_id, name, creator, license, url,
                      file_name, file_size, file_type, sliced_from, status,
                      created_at, updated_at
               FROM things ORDER BY created_at DESC"""
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_thing(thing_id: int) -> bool:
    """Delete a thing row. Returns True if a row was deleted."""
    conn = _get_conn()
    try:
        cursor = conn.execute("DELETE FROM things WHERE id = ?", (thing_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def update_thing_status(thing_id: int, status: str) -> None:
    """Update the status of a thing."""
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE things SET status = ?, updated_at = ? WHERE id = ?",
            (status, _now_iso(), thing_id),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Scanned steps tracking
# ---------------------------------------------------------------------------


def is_step_scanned(step_key: str) -> bool:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT 1 FROM scanned_steps WHERE step_key = ?", (step_key,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def mark_step_scanned(step_key: str) -> None:
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO scanned_steps (step_key) VALUES (?)", (step_key,)
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Print queue
# ---------------------------------------------------------------------------


def add_to_queue(thing_id: int) -> int:
    """Add a thing to the print queue. Returns the position."""
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO print_queue (thing_id, added_at) VALUES (?, ?)",
            (thing_id, _now_iso()),
        )
        conn.commit()
        row = conn.execute("SELECT last_insert_rowid()").fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def get_queue() -> list[dict[str, Any]]:
    """Return queue items joined with thing metadata, ordered by position."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT q.position, q.thing_id, q.added_at,
                   t.name, t.file_name, t.file_type, t.status
            FROM print_queue q
            JOIN things t ON q.thing_id = t.id
            ORDER BY q.position
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def remove_from_queue(position: int) -> bool:
    """Remove a queue item by position. Returns True if removed."""
    conn = _get_conn()
    try:
        cursor = conn.execute("DELETE FROM print_queue WHERE position = ?", (position,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def clear_queue() -> int:
    """Clear the entire queue. Returns count removed."""
    conn = _get_conn()
    try:
        cursor = conn.execute("DELETE FROM print_queue")
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Settings (key-value store)
# ---------------------------------------------------------------------------


def get_setting(key: str) -> str | None:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None
    finally:
        conn.close()


def set_setting(key: str, value: str) -> None:
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()


def get_all_settings() -> dict[str, str]:
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {row["key"]: row["value"] for row in rows}
    finally:
        conn.close()


def delete_setting(key: str) -> bool:
    conn = _get_conn()
    try:
        cursor = conn.execute("DELETE FROM settings WHERE key = ?", (key,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------


def log_message(level: str, message: str) -> None:
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO logs (level, message, created_at) VALUES (?, ?, ?)",
            (level, message, _now_iso()),
        )
        conn.commit()
    finally:
        conn.close()


def get_logs(limit: int = 20, level: str | None = None) -> list[dict[str, Any]]:
    conn = _get_conn()
    try:
        if level:
            rows = conn.execute(
                "SELECT * FROM logs WHERE level = ? ORDER BY id DESC LIMIT ?",
                (level.upper(), limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def clear_logs() -> int:
    conn = _get_conn()
    try:
        cursor = conn.execute("DELETE FROM logs")
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Backups
# ---------------------------------------------------------------------------

BACKUPS_DIR = DB_PATH.parent / "backups"


def create_backup() -> str:
    """Copy the DB to backups dir. Returns the backup filename."""
    import shutil

    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_name = f"printpal-{timestamp}.db"
    backup_path = BACKUPS_DIR / backup_name

    # Close any connections by copying the file directly (WAL mode is safe for copies)
    shutil.copy2(str(DB_PATH), str(backup_path))

    # Prune to last 10
    backups = sorted(BACKUPS_DIR.glob("printpal-*.db"))
    for old in backups[:-10]:
        old.unlink()

    return backup_name


def list_backups() -> list[dict[str, Any]]:
    """List backup files with metadata."""
    if not BACKUPS_DIR.exists():
        return []
    backups = []
    for path in sorted(BACKUPS_DIR.glob("printpal-*.db"), reverse=True):
        backups.append(
            {
                "name": path.name,
                "size": path.stat().st_size,
                "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(
                    timespec="seconds"
                ),
            }
        )
    return backups


def restore_backup(filename: str) -> bool:
    """Restore DB from a backup. Returns True on success."""
    import shutil

    backup_path = BACKUPS_DIR / filename
    if not backup_path.is_file():
        return False
    shutil.copy2(str(backup_path), str(DB_PATH))
    return True
