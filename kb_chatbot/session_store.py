import time
from kb_chatbot.memory import get_memory

# In-memory session store with TTL-based cleanup
SESSION_MEMORY: dict = {}
SESSION_TIMESTAMPS: dict = {}

SESSION_TTL_SECONDS = 3600  # 1 hour


def _evict_expired_sessions():
    now = time.time()
    expired = [sid for sid, ts in SESSION_TIMESTAMPS.items() if now - ts > SESSION_TTL_SECONDS]
    for sid in expired:
        SESSION_MEMORY.pop(sid, None)
        SESSION_TIMESTAMPS.pop(sid, None)


def get_session_memory(session_id: str):
    _evict_expired_sessions()
    if session_id not in SESSION_MEMORY:
        SESSION_MEMORY[session_id] = get_memory(session_id)
    SESSION_TIMESTAMPS[session_id] = time.time()
    return SESSION_MEMORY[session_id]
