from fastapi import FastAPI
from pydantic import BaseModel
from kb_chatbot.retriever import get_retriever
from kb_chatbot.rag_chain import build_rag_chain
from kb_chatbot.session_store import get_session_memory

app = FastAPI(title="Knowledge Base Chatbot")

retriever = get_retriever()
rag_chain = build_rag_chain(get_session_memory)


class Query(BaseModel):
    session_id: str = "default"
    question: str


@app.post("/chat")
def chat(query: Query):
    # Single retrieval — reuse docs for both context and image extraction
    source_docs = retriever.invoke(query.question)
    context = "\n\n".join(doc.page_content for doc in source_docs)

    image_urls = []
    for doc in source_docs:
        image_urls.extend(doc.metadata.get("image_urls", []))

    result = rag_chain.invoke(
        {"question": query.question, "context": context},
        config={"configurable": {"session_id": query.session_id}},
    )

    return {
        "answer": result,
        "images": list(set(image_urls)),
    }
