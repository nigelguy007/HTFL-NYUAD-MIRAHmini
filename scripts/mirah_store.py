"""MIRAH's own records: consent, the audit trail and training examples.

Kept in data/mirah.db, beside the chat software's database. Used by the
consent filter that runs inside the chat software (functions/mirah_gate.py)
and by the host commands (scripts/govern.py). Standard library only, so both
can import it.
"""

from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path

DB_NAME = "mirah.db"
USE = "use"
TRAINING = "training"
PURPOSES = (USE, TRAINING)
AUDIT_RETENTION_DAYS = 365
SECONDS_PER_DAY = 86400
PENDING, APPROVED, REJECTED = "pending", "approved", "rejected"
TRAINING_FILES = ("train.jsonl", "valid.jsonl")

SCHEMA = """
CREATE TABLE IF NOT EXISTS consent (
    id INTEGER PRIMARY KEY,
    user_id TEXT NOT NULL,
    purpose TEXT NOT NULL,
    version TEXT NOT NULL,
    granted_at INTEGER NOT NULL,
    withdrawn_at INTEGER
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY,
    at INTEGER NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS example (
    id INTEGER PRIMARY KEY,
    user_id TEXT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at INTEGER NOT NULL,
    reviewed_by TEXT,
    reviewed_at INTEGER
);
"""

# What is stripped from a training example before a person reviews it. Names in
# ordinary sentences cannot be found by a pattern: that is what the review is for.
SCRUB_PATTERNS = (
    (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[EMAIL]"),
    (re.compile(r"https?://\S+"), "[LINK]"),
    (re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)"), "[NUMBER]"),
    (re.compile(r"(?<!\w)@\w{2,}"), "[HANDLE]"),
)


def connect(data_dir: str | Path) -> sqlite3.Connection:
    # A short wait and write-ahead logging: the chat software and the host
    # commands share this file, and neither may stall the other for long.
    connection = sqlite3.connect(Path(data_dir) / DB_NAME, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.executescript(SCHEMA)
    return connection


def notice_version(notice_text: str) -> str:
    """The version on the notice's first line ("Version: 3"). Changing it asks everyone again."""
    first_line = notice_text.strip().splitlines()[0] if notice_text.strip() else ""
    match = re.match(r"version\s*:\s*(\S+)", first_line, re.IGNORECASE)
    return match.group(1) if match else "1"


# --- Audit trail -----------------------------------------------------------------

def log(connection: sqlite3.Connection, actor: str, action: str, detail: str = "") -> None:
    with connection:
        connection.execute(
            "INSERT INTO audit (at, actor, action, detail) VALUES (?, ?, ?, ?)",
            (int(time.time()), actor, action, detail),
        )


def prune_audit(connection: sqlite3.Connection, now: float | None = None) -> int:
    """Deletes audit entries older than a year. Returns how many went."""
    cutoff = int((now or time.time()) - AUDIT_RETENTION_DAYS * SECONDS_PER_DAY)
    with connection:
        return connection.execute("DELETE FROM audit WHERE at < ?", (cutoff,)).rowcount


def audit_entries(connection: sqlite3.Connection, limit: int = 200) -> list[sqlite3.Row]:
    return connection.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


# --- Consent ---------------------------------------------------------------------

def has_consent(connection: sqlite3.Connection, user_id: str, purpose: str, version: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM consent WHERE user_id = ? AND purpose = ? AND version = ? AND withdrawn_at IS NULL",
        (user_id, purpose, version),
    ).fetchone()
    return row is not None


def grant(connection: sqlite3.Connection, user_id: str, purpose: str, version: str) -> None:
    if has_consent(connection, user_id, purpose, version):
        return
    with connection:
        connection.execute(
            "INSERT INTO consent (user_id, purpose, version, granted_at) VALUES (?, ?, ?, ?)",
            (user_id, purpose, version, int(time.time())),
        )
    log(connection, user_id, f"consent.granted.{purpose}", f"notice version {version}")


def withdraw(connection: sqlite3.Connection, user_id: str, purpose: str) -> bool:
    """Ends every live agreement for this purpose. Returns True if there was one."""
    with connection:
        changed = connection.execute(
            "UPDATE consent SET withdrawn_at = ? WHERE user_id = ? AND purpose = ? AND withdrawn_at IS NULL",
            (int(time.time()), user_id, purpose),
        ).rowcount
    if changed:
        log(connection, user_id, f"consent.withdrawn.{purpose}")
    return bool(changed)


def consent_history(connection: sqlite3.Connection, user_id: str) -> list[sqlite3.Row]:
    return connection.execute("SELECT * FROM consent WHERE user_id = ? ORDER BY id", (user_id,)).fetchall()


# --- Training examples -----------------------------------------------------------

def deidentify(text: str, also_remove: tuple[str, ...] = ()) -> str:
    """Replaces emails, links, long numbers and handles, plus any given names."""
    for pattern, replacement in SCRUB_PATTERNS:
        text = pattern.sub(replacement, text)
    words = {word for name in also_remove for word in (name, *name.split())}
    for word in sorted(words, key=len, reverse=True):
        if len(word) >= 3:
            text = re.sub(re.escape(word), "[NAME]", text, flags=re.IGNORECASE)
    return text


def add_example(connection: sqlite3.Connection, user_id: str, question: str, answer: str) -> None:
    with connection:
        connection.execute(
            "INSERT INTO example (user_id, question, answer, created_at) VALUES (?, ?, ?, ?)",
            (user_id, question, answer, int(time.time())),
        )


def examples(connection: sqlite3.Connection, status: str | None = None) -> list[sqlite3.Row]:
    if status is None:
        return connection.execute("SELECT * FROM example ORDER BY id").fetchall()
    return connection.execute("SELECT * FROM example WHERE status = ? ORDER BY id", (status,)).fetchall()


def trainable_examples(connection: sqlite3.Connection, version: str) -> list[sqlite3.Row]:
    """Approved examples from people whose training consent is still live for this notice."""
    return connection.execute(
        "SELECT * FROM example WHERE status = ? AND user_id IN ("
        " SELECT user_id FROM consent WHERE purpose = ? AND version = ? AND withdrawn_at IS NULL"
        ") ORDER BY id",
        (APPROVED, TRAINING, version),
    ).fetchall()


def review_example(connection: sqlite3.Connection, example_id: int, status: str, reviewer: str) -> bool:
    with connection:
        changed = connection.execute(
            "UPDATE example SET status = ?, reviewed_by = ?, reviewed_at = ? WHERE id = ?",
            (status, reviewer, int(time.time()), example_id),
        ).rowcount
    if changed:
        log(connection, reviewer, f"training.example.{status}", f"example {example_id}")
    return bool(changed)


def clear_training_files(data_dir: str | Path) -> None:
    """Removes the built training set, so a stale copy cannot outlive a withdrawal."""
    for name in TRAINING_FILES:
        (Path(data_dir) / "training" / name).unlink(missing_ok=True)


def delete_examples(connection: sqlite3.Connection, user_id: str, data_dir: str | Path) -> int:
    with connection:
        removed = connection.execute("DELETE FROM example WHERE user_id = ?", (user_id,)).rowcount
    clear_training_files(data_dir)
    return removed


def delete_user(connection: sqlite3.Connection, user_id: str, data_dir: str | Path) -> dict[str, int]:
    """Removes a person's consent records and training examples. The audit trail stays."""
    removed_examples = delete_examples(connection, user_id, data_dir)
    with connection:
        removed_consent = connection.execute("DELETE FROM consent WHERE user_id = ?", (user_id,)).rowcount
    return {"consent_records": removed_consent, "training_examples": removed_examples}
