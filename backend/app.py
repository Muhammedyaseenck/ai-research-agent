import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Make the project folder importable, so we can reuse main.py
sys.path.append(str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field

from main import run_agent, ResearchResponse
from backend import database

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="AI Research Agent API")

# Create the database tables when the server starts (safe to repeat)
database.init_db()


# ---------- Request / response shapes ----------

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = None  # None means "start a new chat"


class ChatResponse(BaseModel):
    conversation_id: str
    report: ResearchResponse


class ConversationSummary(BaseModel):
    id: str
    title: str
    created_at: str


class StoredMessage(BaseModel):
    role: str
    content: str
    report: ResearchResponse | None = None  # only assistant messages have one


class ConversationDetail(ConversationSummary):
    messages: list[StoredMessage]


# ---------- Helpers ----------

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_chat_history(messages: list[dict]):
    """Convert stored messages into LangChain message objects."""
    history = []
    for m in messages:
        if m["role"] == "user":
            history.append(HumanMessage(content=m["content"]))
        else:
            history.append(AIMessage(content=m["content"]))
    return history


def get_conversation_or_404(conv_id: str) -> dict:
    conversation = database.get_conversation(conv_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


# ---------- Endpoints ----------

@app.get("/api/health")
def health_check():
    return {"status": "ok", "message": "Backend is running"}


@app.post("/api/conversations", response_model=ConversationSummary)
def create_conversation():
    conv_id = str(uuid.uuid4())
    created_at = now_iso()
    # Save an empty chat: a conversation row with no messages yet
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO conversations (id, title, created_at) VALUES (?, ?, ?)",
            (conv_id, "New chat", created_at),
        )
    return ConversationSummary(id=conv_id, title="New chat", created_at=created_at)


@app.get("/api/conversations", response_model=list[ConversationSummary])
def list_conversations():
    return database.list_conversations()  # already newest first


@app.get("/api/conversations/{conv_id}", response_model=ConversationDetail)
def get_conversation(conv_id: str):
    return get_conversation_or_404(conv_id)


@app.delete("/api/conversations/{conv_id}")
def delete_conversation(conv_id: str):
    if not database.delete_conversation(conv_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"deleted": conv_id}


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    # 1. Find the conversation, or prepare a new one
    conv_id = request.conversation_id
    if conv_id is None:
        conv_id = str(uuid.uuid4())
        conversation = None            # saved only if the agent succeeds
    else:
        conversation = get_conversation_or_404(conv_id)

    history = build_chat_history(conversation["messages"]) if conversation else []

    # 2. Run the agent with this conversation's history
    try:
        report = run_agent(request.message, chat_history=history)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent failed: {e}")

    # 3. Save the exchange only after success
    if conversation is None:
        title = request.message[:50]
        created_at = now_iso()
    else:
        title = conversation["title"]
        created_at = conversation["created_at"]

    # If a chat still has the placeholder title, name it after the first question
    if title == "New chat":
        title = request.message[:50]
        with database.get_connection() as conn:
            conn.execute(
                "UPDATE conversations SET title = ? WHERE id = ?",
                (title, conv_id),
            )

    database.save_exchange(
        conv_id,
        title,
        created_at,
        request.message,
        f"Topic: {report.topic}\n{report.summary}",
        report.model_dump(),
    )

    return ChatResponse(conversation_id=conv_id, report=report)


# Serve the web page at the root address
@app.get("/", include_in_schema=False)
def serve_index():
    return FileResponse(FRONTEND_DIR / "index.html")


# Serve other files in /frontend (CSS, JS) under /static
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")