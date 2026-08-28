import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.environ["GROQ_API"]
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")  # optional - chỉ cần nếu dùng ChatOpenAI qua OpenRouter
JWT_SECRET_KEY = os.environ["JWT_SECRET_KEY"]  # BẮT BUỘC - dùng chung cho toàn bộ auth, KHÔNG định nghĩa lại ở utils/security.py

PDF_PATH = os.getenv("PDF_PATH", "/home/vinh/vinh/test_ai/unit3/project/FSoft_HR.pdf")
FAISS_INDEX_PATH = os.getenv("FAISS_INDEX_PATH", "faiss_index")

HITL_ENABLED = os.getenv("HITL_ENABLED", "true").lower() in ("1", "true", "yes")

_llm = None
_guardrail_llm = None
_embeddings = None
_groq_client = None


def get_llm():
    """LLM chính dùng cho router/supervisor/agents."""
    global _llm
    if _llm is None:
        from langchain_groq import ChatGroq
        _llm = ChatGroq(model="openai/gpt-oss-120b", api_key=GROQ_API_KEY, temperature=0)
    return _llm


def get_guardrail_llm():
    """LLM riêng cho guardrail."""
    global _guardrail_llm
    if _guardrail_llm is None:
        from langchain_groq import ChatGroq
        _guardrail_llm = ChatGroq(model="openai/gpt-oss-120b", api_key=GROQ_API_KEY, temperature=0)
    return _guardrail_llm


def get_embeddings():
    """Embedding model dùng cho RAG + semantic/episodic memory."""
    global _embeddings
    if _embeddings is None:
        from langchain_huggingface import HuggingFaceEmbeddings
        _embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    return _embeddings


def get_groq_client():
    global _groq_client
    if _groq_client is None:
        from groq import Groq
        _groq_client = Groq(api_key=GROQ_API_KEY)
    return _groq_client


def __getattr__(name: str):
    if name == "llm":
        return get_llm()
    if name == "guardrail_llm":
        return get_guardrail_llm()
    if name == "embeddings":
        return get_embeddings()
    if name == "groq_client":
        return get_groq_client()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")