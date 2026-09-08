import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.environ["GROQ_API"]
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
JWT_SECRET_KEY = os.environ["JWT_SECRET_KEY"]

APP_ENV = os.getenv("APP_ENV", "development").lower()
LOCAL_ENVIRONMENTS = {"development", "dev", "local", "test"}
PDF_PATH = os.getenv("PDF_PATH", "/home/vinh/vinh/test_ai/unit3/project/FSoft_HR.pdf")
FAISS_INDEX_PATH = os.getenv("FAISS_INDEX_PATH", "faiss_index")
RAG_ARTIFACT_URI = os.getenv("RAG_ARTIFACT_URI")
RAG_ARTIFACT_VERSION = os.getenv("RAG_ARTIFACT_VERSION")
RAG_CACHE_DIR = os.getenv("RAG_CACHE_DIR", ".rag-cache")
CHECKPOINT_DATABASE_URL = os.getenv("CHECKPOINT_DATABASE_URL")
HITL_ENABLED = os.getenv("HITL_ENABLED", "true").lower() in ("1", "true", "yes")
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))

_llm = None
_guardrail_llm = None
_embeddings = None
_groq_client = None


def is_local_environment() -> bool:
    return APP_ENV in LOCAL_ENVIRONMENTS


def _to_psycopg_url(database_url: str) -> str:
    """Convert a SQLAlchemy PostgreSQL URL to a psycopg connection URL."""
    parsed = urlsplit(database_url)
    if parsed.scheme.startswith("postgresql+"):
        return urlunsplit(("postgresql", parsed.netloc, parsed.path, parsed.query, parsed.fragment))
    return database_url


def get_checkpoint_database_url() -> str | None:
    """Return a shared PostgreSQL checkpoint URL outside explicit local mode."""
    if CHECKPOINT_DATABASE_URL:
        return _to_psycopg_url(CHECKPOINT_DATABASE_URL)
    if is_local_environment():
        return None
    database_url = os.getenv("DATABASE_URL")
    if database_url and database_url.startswith("postgresql"):
        return _to_psycopg_url(database_url)
    raise RuntimeError("CHECKPOINT_DATABASE_URL or PostgreSQL DATABASE_URL is required outside local development")


def validate_startup_configuration() -> None:
    """Fail fast when production configuration would use local persistence or artifacts."""
    if is_local_environment():
        return
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url.startswith("postgresql"):
        raise RuntimeError("A PostgreSQL DATABASE_URL is required outside local development")
    get_checkpoint_database_url()
    if not RAG_ARTIFACT_URI or not RAG_ARTIFACT_VERSION:
        raise RuntimeError("RAG_ARTIFACT_URI and RAG_ARTIFACT_VERSION are required outside local development")
    if RAG_ARTIFACT_URI.startswith("file://"):
        raise RuntimeError("RAG_ARTIFACT_URI must use remote object storage outside local development")
    if "/" in RAG_ARTIFACT_VERSION or "\\" in RAG_ARTIFACT_VERSION:
        raise RuntimeError("RAG_ARTIFACT_VERSION must be a single version identifier")


def local_rag_paths() -> tuple[Path, Path]:
    return Path(PDF_PATH), Path(FAISS_INDEX_PATH)


def get_llm():
    """Primary LLM used by the router, supervisor, and agents."""
    global _llm
    if _llm is None:
        from langchain_groq import ChatGroq
        _llm = ChatGroq(model="openai/gpt-oss-120b", api_key=GROQ_API_KEY, temperature=0, timeout=LLM_TIMEOUT_SECONDS, max_retries=1)
    return _llm


def get_guardrail_llm():
    """Dedicated LLM used by the guardrail."""
    global _guardrail_llm
    if _guardrail_llm is None:
        from langchain_groq import ChatGroq
        _guardrail_llm = ChatGroq(model="openai/gpt-oss-120b", api_key=GROQ_API_KEY, temperature=0, timeout=LLM_TIMEOUT_SECONDS, max_retries=1)
    return _guardrail_llm


def get_embeddings():
    """Embedding model used by RAG and semantic/episodic memory."""
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
