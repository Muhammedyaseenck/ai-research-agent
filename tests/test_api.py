import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

from backend import app as app_module
from main import ResearchResponse

client = TestClient(app_module.app)

# Records what the fake agent was called with, so tests can inspect it
calls = []


def fake_run_agent(query, chat_history=None):
    calls.append({"query": query, "history_len": len(chat_history or [])})
    return ResearchResponse(
        topic="Fake topic",
        summary=f"Fake answer to: {query}",
        sources=["https://example.com/a"],
        tools_used=["wikipedia"],
    )


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    # Replace the real agent with the fake one, and start each test empty
    monkeypatch.setattr(app_module, "run_agent", fake_run_agent)
    app_module.conversations.clear()
    calls.clear()


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_chat_creates_conversation_and_returns_report():
    r = client.post("/api/chat", json={"message": "Research cats"})
    assert r.status_code == 200
    body = r.json()
    assert body["conversation_id"]
    assert body["report"]["topic"] == "Fake topic"


def test_empty_message_is_rejected():
    r = client.post("/api/chat", json={"message": ""})
    assert r.status_code == 422


def test_too_long_message_is_rejected():
    r = client.post("/api/chat", json={"message": "x" * 2001})
    assert r.status_code == 422


def test_unknown_conversation_returns_404():
    r = client.post(
        "/api/chat", json={"message": "hi", "conversation_id": "nope"}
    )
    assert r.status_code == 404


def test_follow_up_receives_history():
    first = client.post("/api/chat", json={"message": "Research cats"}).json()
    cid = first["conversation_id"]
    client.post(
        "/api/chat", json={"message": "What do they eat?", "conversation_id": cid}
    )
    assert calls[0]["history_len"] == 0   # first message: no history
    assert calls[1]["history_len"] == 2   # second: user + assistant message


def test_conversations_are_isolated():
    a = client.post("/api/chat", json={"message": "Research cats"}).json()
    client.post("/api/chat", json={"message": "Research dogs"})
    assert calls[1]["history_len"] == 0   # a separate chat sees no history
    assert a["conversation_id"] in app_module.conversations


def test_list_open_and_delete():
    cid = client.post("/api/chat", json={"message": "Research cats"}).json()[
        "conversation_id"
    ]

    listed = client.get("/api/conversations").json()
    assert [c["id"] for c in listed] == [cid]
    assert listed[0]["title"] == "Research cats"

    detail = client.get(f"/api/conversations/{cid}").json()
    assert len(detail["messages"]) == 2
    assert detail["messages"][1]["report"]["topic"] == "Fake topic"

    assert client.delete(f"/api/conversations/{cid}").status_code == 200
    assert client.get(f"/api/conversations/{cid}").status_code == 404


def test_failed_agent_leaves_no_empty_chat(monkeypatch):
    def broken(query, chat_history=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(app_module, "run_agent", broken)
    r = client.post("/api/chat", json={"message": "Research cats"})
    assert r.status_code == 500
    assert app_module.conversations == {}