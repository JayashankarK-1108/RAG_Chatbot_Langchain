import os
from langchain_community.vectorstores import Pinecone as LangchainPinecone
from kb_ingestion.embeddings import get_embeddings


def get_vectorstore():
    return LangchainPinecone.from_existing_index(
        os.getenv("PINECONE_INDEX"),
        get_embeddings(),
    )


def get_retriever():
    return get_vectorstore().as_retriever(search_kwargs={"k": 5})
