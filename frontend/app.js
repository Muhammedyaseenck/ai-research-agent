const messagesEl = document.getElementById("messages");
const listEl = document.getElementById("conversation-list");
const form = document.getElementById("chat-form");
const input = document.getElementById("message-input");
const sendBtn = document.getElementById("send-btn");
const newChatBtn = document.getElementById("new-chat-btn");

// Which conversation is open. null means "a new chat that doesn't exist yet".
let conversationId = null;

// ---------- Drawing helpers ----------

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function showEmptyState(text) {
  messagesEl.innerHTML = "";
  const div = document.createElement("div");
  div.className = "empty";
  div.textContent = text;
  messagesEl.appendChild(div);
}

function removeEmptyState() {
  const empty = messagesEl.querySelector(".empty");
  if (empty) empty.remove();
}

function addUserBubble(text) {
  removeEmptyState();
  const div = document.createElement("div");
  div.className = "bubble-user";
  div.textContent = text;           // textContent never runs HTML
  messagesEl.appendChild(div);
  scrollToBottom();
}

function addThinking() {
  const div = document.createElement("div");
  div.className = "thinking";
  div.textContent = "Researching... this can take up to a minute.";
  messagesEl.appendChild(div);
  scrollToBottom();
  return div;
}

function addError(text) {
  const div = document.createElement("div");
  div.className = "error";
  div.textContent = text;
  messagesEl.appendChild(div);
  scrollToBottom();
}

// Only real web links become clickable
function isSafeUrl(value) {
  return /^https?:\/\//i.test(value);
}

function addReport(report) {
  const card = document.createElement("div");
  card.className = "report";

  const title = document.createElement("h2");
  title.textContent = report.topic;
  card.appendChild(title);

  const summary = document.createElement("p");
  summary.className = "summary";
  summary.textContent = report.summary;
  card.appendChild(summary);

  const srcHeading = document.createElement("h3");
  srcHeading.textContent = "Sources";
  card.appendChild(srcHeading);

  if (report.sources.length === 0) {
    const none = document.createElement("p");
    none.className = "muted";
    none.textContent = "No sources were retrieved for this answer.";
    card.appendChild(none);
  } else {
    const list = document.createElement("ul");
    for (const src of report.sources) {
      const li = document.createElement("li");
      if (isSafeUrl(src)) {
        const a = document.createElement("a");
        a.href = src;
        a.textContent = src;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        li.appendChild(a);
      } else {
        li.textContent = src;
      }
      list.appendChild(li);
    }
    card.appendChild(list);
  }

  const toolHeading = document.createElement("h3");
  toolHeading.textContent = "Tools used";
  card.appendChild(toolHeading);

  if (report.tools_used.length === 0) {
    const none = document.createElement("p");
    none.className = "muted";
    none.textContent = "No tools were used.";
    card.appendChild(none);
  } else {
    const chips = document.createElement("div");
    chips.className = "chips";
    for (const tool of report.tools_used) {
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.textContent = tool;
      chips.appendChild(chip);
    }
    card.appendChild(chips);
  }

  messagesEl.appendChild(card);
  scrollToBottom();
}

// ---------- Sidebar ----------

async function loadConversations() {
  try {
    const response = await fetch("/api/conversations");
    const items = await response.json();
    renderConversationList(items);
  } catch (err) {
    listEl.innerHTML = "";
    const li = document.createElement("li");
    li.className = "sidebar-empty";
    li.textContent = "Could not load chats.";
    listEl.appendChild(li);
  }
}

function renderConversationList(items) {
  listEl.innerHTML = "";

  if (items.length === 0) {
    const li = document.createElement("li");
    li.className = "sidebar-empty";
    li.textContent = "No chats yet.";
    listEl.appendChild(li);
    return;
  }

  for (const item of items) {
    const li = document.createElement("li");
    li.className = "conversation-item";
    if (item.id === conversationId) li.classList.add("active");

    const title = document.createElement("span");
    title.className = "title";
    title.textContent = item.title;
    li.appendChild(title);

    const del = document.createElement("button");
    del.className = "delete";
    del.type = "button";
    del.title = "Delete chat";
    del.textContent = "\u2715";       // an "x" symbol
    del.addEventListener("click", (event) => {
      event.stopPropagation();        // don't also open the chat
      deleteConversation(item.id);
    });
    li.appendChild(del);

    li.addEventListener("click", () => openConversation(item.id));
    listEl.appendChild(li);
  }
}

async function openConversation(id) {
  try {
    const response = await fetch("/api/conversations/" + encodeURIComponent(id));
    if (!response.ok) {
      addError("That chat no longer exists.");
      await loadConversations();
      return;
    }
    const data = await response.json();
    conversationId = data.id;

    messagesEl.innerHTML = "";
    if (data.messages.length === 0) {
      showEmptyState("This chat is empty. Ask me to research any topic.");
    }
    for (const m of data.messages) {
      if (m.role === "user") {
        addUserBubble(m.content);
      } else if (m.report) {
        addReport(m.report);
      }
    }
    await loadConversations();        // refresh the highlight
  } catch (err) {
    addError("Could not load that chat.");
  }
}

async function deleteConversation(id) {
  if (!confirm("Delete this chat?")) return;
  try {
    await fetch("/api/conversations/" + encodeURIComponent(id), { method: "DELETE" });
  } catch (err) {
    addError("Could not delete the chat.");
    return;
  }
  if (id === conversationId) {
    conversationId = null;
    showEmptyState("Ask me to research any topic.");
  }
  await loadConversations();
}

function startNewChat() {
  conversationId = null;              // the server creates the chat on the first message
  showEmptyState("New chat started. Ask me to research any topic.");
  loadConversations();                // clears the highlight
  input.focus();
}

// ---------- Sending a message ----------

async function sendMessage(text) {
  addUserBubble(text);
  const thinking = addThinking();
  sendBtn.disabled = true;
  input.disabled = true;

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: text,
        conversation_id: conversationId,
      }),
    });

    const data = await response.json();
    thinking.remove();

    if (!response.ok) {
      addError(typeof data.detail === "string" ? data.detail : "Something went wrong.");
      return;
    }

    conversationId = data.conversation_id;
    addReport(data.report);
    await loadConversations();        // new chats appear in the sidebar
  } catch (err) {
    thinking.remove();
    addError("Could not reach the server. Is it running?");
  } finally {
    sendBtn.disabled = false;
    input.disabled = false;
    input.focus();
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  sendMessage(text);
});

// Enter sends, Shift+Enter makes a new line
input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

newChatBtn.addEventListener("click", startNewChat);

// ---------- Start-up ----------
showEmptyState("Ask me to research any topic.");
loadConversations();