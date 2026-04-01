
from langchain_openai import ChatOpenAI
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from kb_chatbot.prompt import RAG_PROMPT


def build_rag_chain(get_session_history):
    """
    Builds a conversational RAG chain compatible with LangChain v0.3+.

    The chain expects pre-fetched context to be passed in the input dict,
    so retrieval is handled externally (in the API layer) to avoid redundant
    vector store calls.

    Args:
        get_session_history: A callable(session_id) -> BaseChatMessageHistory.

    Returns:
        A RunnableWithMessageHistory chain that accepts
        {"question": str, "context": str}.
    """
    llm = ChatOpenAI(model="gpt-4o", temperature=0.2)

    prompt = ChatPromptTemplate.from_messages([
        ("system", RAG_PROMPT.template),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{question}"),
    ])

    rag_chain = prompt | llm | StrOutputParser()

    return RunnableWithMessageHistory(
        rag_chain,
        get_session_history,
        input_messages_key="question",
        history_messages_key="chat_history",
    )
