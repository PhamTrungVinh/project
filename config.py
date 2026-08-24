import os
from dotenv import load_dotenv
from groq import Groq
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langchain_huggingface import HuggingFaceEmbeddings

load_dotenv()

GROQ_API_KEY = os.environ["GROQ_API"]
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
JWT_SECRET_KEY = os.environ["JWT_SECRET_KEY"]

PDF_PATH = "/home/vinh/vinh/test_ai/unit3/project/FSoft_HR.pdf"
FAISS_INDEX_PATH = "faiss_index"

# LLM used for router + web agent
# llm = ChatOpenAI(
#     model="nvidia/nemotron-3-ultra-550b-a55b:free",
#     api_key=OPENROUTER_API_KEY,
#     base_url="https://openrouter.ai/api/v1",
#     temperature=0,
# )

llm = ChatGroq(
    model="openai/gpt-oss-120b",
    api_key=GROQ_API_KEY,
    temperature=0,
)

#LLM used for guardrail 
guardrail_llm = ChatGroq(
    model="openai/gpt-oss-120b",
    api_key=GROQ_API_KEY,
    temperature=0,
)

groq_client = Groq(api_key=GROQ_API_KEY)

# Embedding model for RAG
embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

# Enable or disable Human-in-the-Loop, can be configured using the `HITL_ENABLED=false` environment variable.
HITL_ENABLED = os.getenv("HITL_ENABLED", "true").lower() in ("1", "true", "yes")
