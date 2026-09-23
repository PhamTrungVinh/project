from rag.storage import get_rag_artifact_paths
from services.ai_adapter import get_embeddings

_resources = None


def build_rag_resources(*, allow_index_build: bool = False):
    global _resources
    if _resources is not None:
        return _resources

    from langchain_community.document_loaders import PyPDFLoader
    from langchain_community.vectorstores import FAISS
    from langchain_experimental.text_splitter import SemanticChunker
    from langchain_community.retrievers import BM25Retriever
    from sentence_transformers import CrossEncoder

    embeddings = get_embeddings()
    pdf_path, faiss_index_path = get_rag_artifact_paths()

    loader = PyPDFLoader(str(pdf_path))
    docs = loader.load()

    text_splitter = SemanticChunker(embeddings)
    all_splits = text_splitter.split_documents(docs)

    reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

    index_files_exist = (
        (faiss_index_path / "index.faiss").exists()
        and (faiss_index_path / "index.pkl").exists()
    )

    if index_files_exist:
        vector_store = FAISS.load_local(str(faiss_index_path), embeddings, allow_dangerous_deserialization=True)
    elif allow_index_build:
        vector_store = FAISS.from_documents(all_splits, embeddings)
        vector_store.save_local(str(faiss_index_path))
    else:
        raise RuntimeError("RAG index is unavailable. Build and publish an approved artifact before serving queries.")

    dense = vector_store.as_retriever(search_type="similarity", search_kwargs={"k": 50})
    bm25 = BM25Retriever.from_documents(all_splits)
    bm25.k = 50

    _resources = {"dense": dense, "bm25": bm25, "reranker": reranker}
    return _resources