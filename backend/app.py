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

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="AI Research Agent API")

# In-memory store:
# {conversation_id: {"title": str, "created_at": str, "messages": [...]}}
# Lost when the server restarts. We'll replace it with a database later.
conversations: dict[str, dict] = {}


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
    if conv_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversations[conv_id]


# ---------- Endpoints ----------

@app.get("/api/health")
def health_check():
    return {"status": "ok", "message": "Backend is running"}


@app.post("/api/conversations", response_model=ConversationSummary)
def create_conversation():
    conv_id = str(uuid.uuid4())
    conversations[conv_id] = {
        "title": "New chat",
        "created_at": now_iso(),
        "messages": [],
    }
    return ConversationSummary(
        id=conv_id,
        title="New chat",
        created_at=conversations[conv_id]["created_at"],
    )


@app.get("/api/conversations", response_model=list[ConversationSummary])
def list_conversations():
    items = [
        ConversationSummary(id=cid, title=c["title"], created_at=c["created_at"])
        for cid, c in conversations.items()
    ]
    items.sort(key=lambda c: c.created_at, reverse=True)  # newest first
    return items


@app.get("/api/conversations/{conv_id}", response_model=ConversationDetail)
def get_conversation(conv_id: str):
    c = get_conversation_or_404(conv_id)
    return ConversationDetail(
        id=conv_id,
        title=c["title"],
        created_at=c["created_at"],
        messages=c["messages"],
    )


@app.delete("/api/conversations/{conv_id}")
def delete_conversation(conv_id: str):
    get_conversation_or_404(conv_id)
    del conversations[conv_id]
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
        conversation = {
            "title": request.message[:50],
            "created_at": now_iso(),
            "messages": [],
        }
        conversations[conv_id] = conversation

    conversation["messages"].append(
        {"role": "user", "content": request.message}
    )
    conversation["messages"].append(
        {
            "role": "assistant",
            "content": f"Topic: {report.topic}\n{report.summary}",
            "report": report.model_dump(),
        }
    )

    return ChatResponse(conversation_id=conv_id, report=report)


# Serve the web page at the root address
@app.get("/", include_in_schema=False)
def serve_index():
    return FileResponse(FRONTEND_DIR / "index.html")


# Serve other files in /frontend (CSS, JS) under /static
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")