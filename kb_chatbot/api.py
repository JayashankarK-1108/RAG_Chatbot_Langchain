import uuid
import os
import re
import json
import pathlib
from datetime import datetime, timezone
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
OUT_OF_CONTEXT_THRESHOLD = 0.45

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS_DIR = _PROJECT_ROOT / "data" / "documents"
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md"}
KB_REQUESTS_FILE = _PROJECT_ROOT / "data" / "kb_requests.json"


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


def _inject_image_markers(text: str, num_images: int) -> str:
    """
    Post-processing fallback for PDF mode: if the LLM didn't place [IMAGE_N] markers
    after each numbered step, inject them automatically.
    Splits on double-newlines; any block that starts with a digit step (1. / 2) / etc.)
    gets a marker appended after it, cycling through the available image count.
    """
    if num_images == 0 or "[IMAGE_" in text:
        return text  # markers already present or no images — nothing to do

    parts = re.split(r"(\n\n)", text)
    out = []
    img_idx = 1

    for part in parts:
        out.append(part)
        if part.strip() and re.match(r"^\d+[.)]\s", part.strip()):
            n = ((img_idx - 1) % num_images) + 1
            out.append(f"\n[IMAGE_{n}]")
            img_idx += 1

    return "".join(out)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/library")
def get_library():
    """Return a list of available document titles in the knowledge base."""
    if not DOCS_DIR.exists():
        return {"documents": []}

    docs = []
    for f in sorted(DOCS_DIR.iterdir()):
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
            # Strip all known extensions (handles double extensions like .pdf.pdf)
            name = f.name
            name = re.sub(r"(\.\w+)+$", "", name)
            name = name.replace("_", " ").replace("-", " ").strip()
            docs.append({"filename": f.name, "title": name})

    return {"documents": docs}


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

    # Retrieve a wide pool of candidates so long step-by-step docs aren't truncated
    results = vectorstore.similarity_search_with_relevance_scores(query.question, k=20)

    # Out-of-context guard: if the best match score is too low, the question is unrelated
    if not results or results[0][1] < OUT_OF_CONTEXT_THRESHOLD:
        return {
            "session_id": session_id,
            "answer": (
                "I'm sorry, but your question appears to be **outside the scope** of our knowledge base. "
                "Please check the **Library** (bottom-left) for available documents and ask a question related to those topics."
            ),
            "images": [],
        }

    # Identify the most relevant document from the top result
    top_source = results[0][0].metadata.get("source", "") if results else None

    # For the top source: include ALL its chunks (no threshold) so no step is skipped.
    # For other sources: apply the score threshold to avoid unrelated noise.
    top_source_all = [doc for doc, _ in results if doc.metadata.get("source") == top_source]
    other_filtered = [
        doc for doc, score in results
        if doc.metadata.get("source") != top_source and score >= SCORE_THRESHOLD
    ]
    source_docs = top_source_all + other_filtered

    # Fallback: if the top source itself had no hits (shouldn't happen), use raw top-3
    if not source_docs:
        source_docs = [doc for doc, _ in results[:3]]

    top_source_docs = [doc for doc in source_docs if doc.metadata.get("source") == top_source]
    other_docs = [doc for doc in source_docs if doc.metadata.get("source") != top_source]

    # Detect whether the top source was ingested with per-step image positioning (DOCX)
    uses_positioned_images = any(
        doc.metadata.get("image_order") == "positioned" for doc in top_source_docs
    )

    seen_keys: list = []

    if uses_positioned_images:
        # DOCX: embed [IMAGE_N] markers directly after each chunk that has an associated image.
        # The LLM sees the correct position and simply preserves the markers.
        context_parts = []
        img_counter = 0
        for doc in top_source_docs:
            chunk_text = doc.page_content
            chunk_image_urls = doc.metadata.get("image_urls", [])

            # Collect markers for every image belonging to this step (may be 2+)
            step_markers = []
            for url in chunk_image_urls:
                key = _s3_key_from_url(url)
                if key and key not in seen_keys:
                    seen_keys.append(key)
                    img_counter += 1
                    step_markers.append(f"[IMAGE_{img_counter}]")

            if step_markers:
                context_parts.append(chunk_text + "\n" + "\n".join(step_markers))
            else:
                context_parts.append(chunk_text)

        for doc in other_docs:
            context_parts.append(doc.page_content)

        context = "\n\n".join(context_parts)
        image_refs = "Images are embedded in the context above."
    else:
        # PDF / other: existing bulk approach — collect all images from top source
        context = "\n\n".join(doc.page_content for doc in source_docs)
        for doc in top_source_docs:
            for stored_url in doc.metadata.get("image_urls", []):
                key = _s3_key_from_url(stored_url)
                if key and key not in seen_keys:
                    seen_keys.append(key)

        image_refs = "\n".join(f"[IMAGE_{i+1}]" for i in range(len(seen_keys)))
        if not image_refs:
            image_refs = "No images available."

    # Proxy URLs returned to the frontend — always fresh
    proxy_urls = [f"/image-proxy?key={key}" for key in seen_keys]

    result = rag_chain.invoke(
        {"question": query.question, "context": context, "image_refs": image_refs},
        config={"configurable": {"session_id": session_id}},
    )

    # For PDF mode: if the LLM forgot to place markers, inject them after each numbered step
    if not uses_positioned_images and seen_keys:
        result = _inject_image_markers(result, len(seen_keys))

    set_session_title(session_id, query.question)

    return {
        "session_id": session_id,
        "answer": result,
        "images": proxy_urls,
    }


class KBRequestBody(BaseModel):
    question: str = ""
    comment: str


@app.post("/kb-request")
def submit_kb_request(body: KBRequestBody):
    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "question": body.question,
        "comment": body.comment,
    }
    existing = []
    if KB_REQUESTS_FILE.exists():
        try:
            existing = json.loads(KB_REQUESTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            existing = []
    existing.append(entry)
    KB_REQUESTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    KB_REQUESTS_FILE.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"status": "submitted", "id": entry["id"]}


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
