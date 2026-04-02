import uuid
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from kb_chatbot.retriever import get_retriever
from kb_chatbot.rag_chain import build_rag_chain
from kb_chatbot.session_store import (
    get_session_memory,
    set_session_title,
    list_sessions,
    delete_session,
    SESSION_MEMORY,
)

app = FastAPI(title="Knowledge Base Chatbot")

retriever = get_retriever()
rag_chain = build_rag_chain(get_session_memory)


@app.get("/health")
def health():
    return {"status": "ok"}


class Query(BaseModel):
    session_id: str = ""
    question: str


@app.post("/chat")
def chat(query: Query):
    session_id = query.session_id or str(uuid.uuid4())

    source_docs = retriever.invoke(query.question)
    context = "\n\n".join(doc.page_content for doc in source_docs)

    image_urls = []
    for doc in source_docs:
        image_urls.extend(doc.metadata.get("image_urls", []))

    result = rag_chain.invoke(
        {"question": query.question, "context": context},
        config={"configurable": {"session_id": session_id}},
    )

    set_session_title(session_id, query.question)

    return {
        "session_id": session_id,
        "answer": result,
        "images": list(set(image_urls)),
    }


@app.get("/sessions")
def get_sessions():
    return list_sessions()


@app.get("/sessions/{session_id}/history")
def get_history(session_id: str):
    memory = SESSION_MEMORY.get(session_id)
    if not memory:
        return {"messages": []}
    messages = [
        {"role": "human" if m.type == "human" else "ai", "content": m.content}
        for m in memory.messages
    ]
    return {"messages": messages}


@app.delete("/sessions/{session_id}")
def remove_session(session_id: str):
    delete_session(session_id)
    return {"status": "deleted"}


app.mount("/", StaticFiles(directory="static", html=True), name="static")
