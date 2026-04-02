let currentSessionId = null;
let currentMessages = []; // tracks messages for the active session

const STORAGE_KEY = "rag_sessions";

// ── LocalStorage helpers ──────────────────────────────────────────────
function storageAll() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}"); }
  catch { return {}; }
}

function storageSave() {
  if (!currentSessionId) return;
  const all = storageAll();
  const existing = all[currentSessionId] || {};
  all[currentSessionId] = {
    title: existing.title || "New Chat",
    messages: currentMessages,
    ts: Date.now(),
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(all));
}

function storageSetTitle(sessionId, title) {
  const all = storageAll();
  all[sessionId] = {
    ...(all[sessionId] || { messages: [] }),
    title: title.slice(0, 60),
    ts: Date.now(),
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(all));
}

function storageDelete(sessionId) {
  const all = storageAll();
  delete all[sessionId];
  localStorage.setItem(STORAGE_KEY, JSON.stringify(all));
}

// ── Init ──────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  renderSessionListFromStorage();
  document.getElementById("newChatBtn").addEventListener("click", startNewChat);
  document.getElementById("lightbox").addEventListener("click", (e) => {
    if (e.target === e.currentTarget || e.target.classList.contains("lightbox-close")) {
      closeLightbox();
    }
  });
});

// ── Session management ────────────────────────────────────────────────
function renderSessionListFromStorage() {
  const all = storageAll();
  const sessions = Object.entries(all)
    .map(([id, data]) => ({ session_id: id, title: data.title || "New Chat", last_active: data.ts || 0 }))
    .sort((a, b) => b.last_active - a.last_active);
  renderSessionList(sessions);
}

function renderSessionList(sessions) {
  const list = document.getElementById("sessionList");
  list.innerHTML = "";

  if (!sessions.length) {
    list.innerHTML = '<li style="padding:10px 10px;font-size:12px;color:var(--text-muted)">No chats yet</li>';
    return;
  }

  sessions.forEach((s) => {
    const li = document.createElement("li");
    li.className = "session-item" + (s.session_id === currentSessionId ? " active" : "");
    li.dataset.id = s.session_id;
    li.innerHTML = `
      <span class="session-title" title="${escapeHtml(s.title)}">${escapeHtml(s.title)}</span>
      <button class="delete-btn" title="Delete chat" onclick="deleteSession(event, '${s.session_id}')">✕</button>
    `;
    li.addEventListener("click", () => loadSession(s.session_id));
    list.appendChild(li);
  });
}

function loadSession(sessionId) {
  currentSessionId = sessionId;
  const all = storageAll();
  const session = all[sessionId];
  currentMessages = session?.messages || [];

  clearMessages();

  if (currentMessages.length === 0) {
    document.getElementById("welcomeMsg").style.display = "flex";
  } else {
    document.getElementById("welcomeMsg").style.display = "none";
    currentMessages.forEach((m) => appendMessage(m.role, m.content, m.images || []));
    scrollToBottom();
  }

  highlightActiveSession();
}

function deleteSession(event, sessionId) {
  event.stopPropagation();
  storageDelete(sessionId);
  fetch(`/sessions/${sessionId}`, { method: "DELETE" });
  if (currentSessionId === sessionId) startNewChat();
  else renderSessionListFromStorage();
}

function startNewChat() {
  currentSessionId = null;
  currentMessages = [];
  clearMessages();
  highlightActiveSession();
}

function highlightActiveSession() {
  document.querySelectorAll(".session-item").forEach((el) => {
    el.classList.toggle("active", el.dataset.id === currentSessionId);
  });
}

// ── Messaging ─────────────────────────────────────────────────────────
async function sendMessage() {
  const input = document.getElementById("userInput");
  const question = input.value.trim();
  if (!question) return;

  document.getElementById("welcomeMsg").style.display = "none";
  input.value = "";
  autoResize(input);
  setInputDisabled(true);

  appendMessage("human", question);
  const typingId = appendTyping();
  scrollToBottom();

  try {
    const res = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: currentSessionId || "", question }),
    });

    const data = await res.json();
    removeTyping(typingId);

    if (!currentSessionId) {
      currentSessionId = data.session_id;
      storageSetTitle(currentSessionId, question);
    }

    appendMessage("ai", data.answer, data.images || []);

    // Persist both messages to localStorage
    currentMessages.push({ role: "human", content: question, images: [] });
    currentMessages.push({ role: "ai", content: data.answer, images: data.images || [] });
    storageSave();

    renderSessionListFromStorage();
    highlightActiveSession();
    scrollToBottom();
  } catch (err) {
    removeTyping(typingId);
    appendMessage("ai", "Something went wrong. Please try again.");
  } finally {
    setInputDisabled(false);
    document.getElementById("userInput").focus();
  }
}

function handleKey(event) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
}

// ── DOM helpers ───────────────────────────────────────────────────────
function appendMessage(role, content, images = []) {
  const container = document.getElementById("chatMessages");

  const row = document.createElement("div");
  row.className = `message-row ${role}`;

  const isHuman = role === "human";
  const avatarLabel = isHuman ? "U" : "AI";
  const avatarClass = isHuman ? "human-avatar" : "ai-avatar";

  row.innerHTML = `
    <div class="message-wrapper">
      <div class="avatar ${avatarClass}">${avatarLabel}</div>
      <div class="bubble">${formatContent(content, images)}</div>
    </div>
  `;

  container.appendChild(row);
  return row;
}

function appendTyping() {
  const container = document.getElementById("chatMessages");
  const row = document.createElement("div");
  row.className = "message-row ai";
  const id = "typing-" + Date.now();
  row.id = id;
  row.innerHTML = `
    <div class="message-wrapper">
      <div class="avatar ai-avatar">AI</div>
      <div class="bubble">
        <div class="typing-indicator"><span></span><span></span><span></span></div>
      </div>
    </div>
  `;
  container.appendChild(row);
  return id;
}

function removeTyping(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

function clearMessages() {
  const container = document.getElementById("chatMessages");
  container.innerHTML = `
    <div class="welcome" id="welcomeMsg">
      <div class="welcome-icon">
        <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
        </svg>
      </div>
      <h2>How can I help you today?</h2>
      <p>Ask anything about the knowledge base documents.</p>
    </div>
  `;
}

function scrollToBottom() {
  const container = document.getElementById("chatMessages");
  container.scrollTop = container.scrollHeight;
}

function setInputDisabled(disabled) {
  document.getElementById("userInput").disabled = disabled;
  document.getElementById("sendBtn").disabled = disabled;
}

function autoResize(el) {
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 180) + "px";
}

// ── Lightbox ──────────────────────────────────────────────────────────
function openLightbox(url) {
  const lb = document.getElementById("lightbox");
  document.getElementById("lightboxImg").src = url;
  lb.classList.add("open");
}

function closeLightbox() {
  document.getElementById("lightbox").classList.remove("open");
}

// ── Utils ─────────────────────────────────────────────────────────────
function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatContent(text, images = []) {
  // Replace [IMAGE_N] markers with actual inline images
  text = text.replace(/\[IMAGE_(\d+)\]/g, (_, n) => {
    const url = images[parseInt(n) - 1];
    if (!url) return "";
    return `<div class="inline-image-wrap">
      <img src="${escapeHtml(url)}" alt="Step screenshot" class="inline-img" onclick="openLightbox('${escapeHtml(url)}')" />
    </div>`;
  });
  // Bold: **text**
  text = text.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
  // Italic: *text*
  text = text.replace(/\*(.*?)\*/g, "<em>$1</em>");
  // Inline code: `code`
  text = text.replace(/`([^`]+)`/g, "<code>$1</code>");
  // Newlines to <br>
  text = text.replace(/\n/g, "<br>");
  return text;
}
