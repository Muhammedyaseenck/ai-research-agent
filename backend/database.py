import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

# The database is one file called chats.db in your project folder
DB_PATH = Path(__file__).resolve().parent.parent / "chats.db"


@contextmanager
def get_connection():
    """Open the database, save changes when done, and always close it."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row            # lets us read columns by name
    conn.execute("PRAGMA foreign_keys = ON")  # deleting a chat deletes its messages
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create the tables if they don't exist yet. Safe to run many times."""
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                report_json TEXT,
                FOREIGN KEY (conversation_id)
                    REFERENCES conversations(id) ON DELETE CASCADE
            )
            """
        )


def conversation_exists(conv_id):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
    return row is not None


def list_conversations():
    """Return all chats, newest first."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, title, created_at FROM conversations "
            "ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_conversation(conv_id):
    """Return one chat with its messages, or None if it doesn't exist."""
    with get_connection() as conn:
        conv = conn.execute(
            "SELECT id, title, created_at FROM conversations WHERE id = ?",
            (conv_id,),
        ).fetchone()
        if conv is None:
            return None

        rows = conn.execute(
            "SELECT role, content, report_json FROM messages "
            "WHERE conversation_id = ? ORDER BY id",
            (conv_id,),
        ).fetchall()

    messages = []
    for r in rows:
        report = json.loads(r["report_json"]) if r["report_json"] else None
        messages.append(
            {"role": r["role"], "content": r["content"], "report": report}
        )

    result = dict(conv)
    result["messages"] = messages
    return result


def save_exchange(conv_id, title, created_at, user_text, assistant_text, report):
    """Save one question and its answer.
    Creates the chat first if it is new. All steps succeed or none do."""
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO conversations (id, title, created_at) "
            "VALUES (?, ?, ?)",
            (conv_id, title, created_at),
        )
        conn.execute(
            "INSERT INTO messages (conversation_id, role, content, report_json) "
            "VALUES (?, 'user', ?, NULL)",
            (conv_id, user_text),
        )
        conn.execute(
            "INSERT INTO messages (conversation_id, role, content, report_json) "
            "VALUES (?, 'assistant', ?, ?)",
            (conv_id, assistant_text, json.dumps(report)),
        )


def delete_conversation(conv_id):
    """Delete a chat and its messages. Returns True if it existed."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM conversations WHERE id = ?", (conv_id,)
        )
    return cursor.rowcount > 0