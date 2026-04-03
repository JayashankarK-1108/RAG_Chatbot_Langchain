import uuid
import os
import boto3
from urllib.parse import urlparse
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from kb_chatbot.retriever import get_vectorstore
from kb_chatbot.rag_chain import build_rag_chain
from kb_chatbot.session_store import (
    get_session_memory,
    set_session_title,
    list_sessions,
    delete_session,
    SESSION_MEMORY,
)

app = FastAPI(title="Knowledge Base Chatbot")

vectorstore = get_vectorstore()
rag_chain = build_rag_chain(get_session_memory)

SCORE_THRESHOLD = 0.60


def _s3_key_from_url(stored_url: str) -> str:
    """Extract S3 object key from a stored s3:// or https:// URL."""
    parsed = urlparse(stored_url)
    if parsed.scheme == "s3":
        return parsed.path.lstrip("/")
    # https://bucket.s3.amazonaws.com/key?...
    return parsed.path.lstrip("/")


def _fresh_presigned_url(key: str) -> str:
    s3 = boto3.client(
        "s3",
        region_name=os.getenv("AWS_REGION"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": os.getenv("S3_BUCKET_NAME"), "Key": key},
        ExpiresIn=3600,
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/image-proxy")
def image_proxy(key: str):
    """Generate a fresh presigned URL and redirect to it."""
    url = _fresh_presigned_url(key)
    return RedirectResponse(url)


class Query(BaseModel):
    session_id: str = ""
    question: str


@app.post("/chat")
def chat(query: Query):
    session_id = query.session_id or str(uuid.uuid4())

    # Score-filtered retrieval — suppresses images for irrelevant queries like "hi"
    results = vectorstore.similarity_search_with_relevance_scores(query.question, k=8)
    source_docs = [doc for doc, score in results if score >= SCORE_THRESHOLD]

    # Fallback: if nothing clears the threshold, use top-3 results anyway
    if not source_docs:
        source_docs = [doc for doc, _ in results[:3]]

    context = "\n\n".join(doc.page_content for doc in source_docs)

    # Find the dominant source document (most chunks retrieved from it)
    source_counter: dict = {}
    for doc in source_docs:
        src = doc.metadata.get("source", "")
        source_counter[src] = source_counter.get(src, 0) + 1
    dominant_source = max(source_counter, key=source_counter.get) if source_counter else None

    # Collect images only from the dominant source — prevents cross-doc image bleed
    seen_keys: list = []
    for doc in source_docs:
        if doc.metadata.get("source") != dominant_source:
            continue
        for stored_url in doc.metadata.get("image_urls", []):
            key = _s3_key_from_url(stored_url)
            if key and key not in seen_keys:
                seen_keys.append(key)

    # Build image reference list for the prompt (e.g. "[IMAGE_1]", "[IMAGE_2]")
    image_refs = "\n".join(f"[IMAGE_{i+1}]" for i in range(len(seen_keys)))
    if not image_refs:
        image_refs = "No images available."

    # Proxy URLs returned to the frontend — always fresh
    proxy_urls = [f"/image-proxy?key={key}" for key in seen_keys]

    result = rag_chain.invoke(
        {"question": query.question, "context": context, "image_refs": image_refs},
        config={"configurable": {"session_id": session_id}},
    )

    set_session_title(session_id, query.question)

    return {
        "session_id": session_id,
        "answer": result,
        "images": proxy_urls,
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
