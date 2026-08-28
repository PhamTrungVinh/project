from config import get_llm, get_guardrail_llm, get_embeddings, get_groq_client


def embed_text(text: str) -> list[float]:
    return get_embeddings().embed_query(text)


def embed_texts(texts: list[str]) -> list[list[float]]:
    return get_embeddings().embed_documents(texts)


def get_chat_llm():
    return get_llm()


def get_safety_llm():
    return get_guardrail_llm()


def get_raw_groq_client():
    return get_groq_client()