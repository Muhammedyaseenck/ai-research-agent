import sys
from pathlib import Path

# Make the project folder importable
sys.path.append(str(Path(__file__).resolve().parent.parent))

from backend import database

# Use a separate test file, so the real chats.db is never touched
test_db = Path(__file__).resolve().parent / "test_chats.db"
if test_db.exists():
    test_db.unlink()
database.DB_PATH = test_db

database.init_db()
print("1. Tables created")

fake_report = {
    "topic": "Messi",
    "summary": "A football player.",
    "sources": ["https://en.wikipedia.org/wiki/Lionel_Messi"],
    "tools_used": ["wikipedia"],
}

database.save_exchange(
    "chat-1", "Who is Messi", "2026-11-02T08:00:00",
    "Who is Messi", "Topic: Messi\nA football player.", fake_report,
)
print("2. Saved one exchange")

print("3. List:", database.list_conversations())

chat = database.get_conversation("chat-1")
print("4. Message count:", len(chat["messages"]))
print("5. Report back:", chat["messages"][1]["report"]["topic"])

print("6. Exists:", database.conversation_exists("chat-1"))
print("7. Deleted:", database.delete_conversation("chat-1"))
print("8. List after delete:", database.list_conversations())

test_db.unlink()
print("Done. Test file removed.")