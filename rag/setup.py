import os
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import FAISS
from langchain_experimental.text_splitter import SemanticChunker
from langchain_community.retrievers import BM25Retriever
from sentence_transformers import CrossEncoder

from config import PDF_PATH, FAISS_INDEX_PATH, embeddings

_resources = None  # cache singleton trong process


def build_rag_resources():
    """Trả về dict chứa {dense, bm25, reranker}. Chỉ build thật sự lần đầu gọi."""
    global _resources
    if _resources is not None:
        return _resources

    loader = PyPDFLoader(PDF_PATH)
    docs = loader.load()

    text_splitter = SemanticChunker(embeddings)
    all_splits = text_splitter.split_documents(docs)

    reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

    if os.path.exists(FAISS_INDEX_PATH):
        vector_store = FAISS.load_local(
            FAISS_INDEX_PATH,
            embeddings,
            allow_dangerous_deserialization=True,
        )
    else:
        vector_store = FAISS.from_documents(all_splits, embeddings)
        vector_store.save_local(FAISS_INDEX_PATH)

    dense = vector_store.as_retriever(
        search_type="similarity",
        search_kwargs={"k": 50},
    )

    bm25 = BM25Retriever.from_documents(all_splits)
    bm25.k = 50

    _resources = {
        "dense": dense,
        "bm25": bm25,
        "reranker": reranker,
    }
    return _resources
