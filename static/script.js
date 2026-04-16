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
  document.getElementById("libraryBtn").addEventListener("click", openLibrary);
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

  const title = session?.title || "New Chat";
  document.getElementById("chatTitle").textContent = title;

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
  document.getElementById("chatTitle").textContent = "New Chat";
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
  const avatarClass = isHuman ? "human-avatar" : "ai-avatar";
  const avatarContent = isHuman
    ? "U"
    : `<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" width="16" height="16">
        <polygon points="50,4 96,28 96,72 50,96 4,72 4,28" fill="#f97316"/>
        <polygon points="50,20 82,37 82,63 50,80 18,63 18,37" fill="none" stroke="rgba(255,255,255,0.55)" stroke-width="5"/>
       </svg>`;

  row.innerHTML = `
    <div class="message-wrapper">
      <div class="avatar ${avatarClass}">${avatarContent}</div>
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
      <div class="avatar ai-avatar">
        <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" width="16" height="16">
          <polygon points="50,4 96,28 96,72 50,96 4,72 4,28" fill="#f97316"/>
          <polygon points="50,20 82,37 82,63 50,80 18,63 18,37" fill="none" stroke="rgba(255,255,255,0.55)" stroke-width="5"/>
        </svg>
      </div>
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
        <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" width="36" height="36">
          <polygon points="50,4 96,28 96,72 50,96 4,72 4,28" fill="#f97316"/>
          <polygon points="50,20 82,37 82,63 50,80 18,63 18,37" fill="none" stroke="rgba(255,255,255,0.55)" stroke-width="4"/>
        </svg>
      </div>
      <h2>How can I help you today?</h2>
      <p>Ask me anything about the knowledge base. I'll find the relevant steps and screenshots for you.</p>
      <div class="suggestions">
        <button class="suggestion-chip" onclick="useSuggestion('How do I configure WLAN?')">How do I configure WLAN?</button>
        <button class="suggestion-chip" onclick="useSuggestion('Walk me through the proxy process')">Walk me through the proxy process</button>
        <button class="suggestion-chip" onclick="useSuggestion('Show me the pivot process steps')">Show me the pivot process steps</button>
      </div>
    </div>
  `;
}

function useSuggestion(text) {
  const input = document.getElementById("userInput");
  input.value = text;
  autoResize(input);
  sendMessage();
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

// ── Library ───────────────────────────────────────────────────────────
async function openLibrary() {
  const modal = document.getElementById("libraryModal");
  const list = document.getElementById("libraryDocList");
  modal.classList.add("open");
  document.getElementById("libraryBtn").classList.add("active");

  list.innerHTML = '<li class="library-loading">Loading documents…</li>';

  try {
    const res = await fetch("/library");
    const data = await res.json();
    const docs = data.documents || [];

    if (!docs.length) {
      list.innerHTML = '<li class="library-loading">No documents found.</li>';
      return;
    }

    list.innerHTML = "";
    docs.forEach((doc) => {
      const li = document.createElement("li");
      li.className = "library-doc-item";
      li.innerHTML = `
        <div class="library-doc-icon">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none"
            stroke="#f97316" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
            <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
          </svg>
        </div>
        <span class="library-doc-name">${escapeHtml(doc.title)}</span>
      `;
      list.appendChild(li);
    });
  } catch {
    list.innerHTML = '<li class="library-loading">Failed to load documents.</li>';
  }
}

function closeLibrary() {
  document.getElementById("libraryModal").classList.remove("open");
  document.getElementById("libraryBtn").classList.remove("active");
}

function handleLibraryOverlayClick(e) {
  if (e.target === e.currentTarget) closeLibrary();
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
