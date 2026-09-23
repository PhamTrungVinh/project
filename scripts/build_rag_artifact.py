"""Explicit offline RAG-index build; never call this from request-serving code."""

from rag.setup import build_rag_resources


if __name__ == "__main__":
    build_rag_resources(allow_index_build=True)
    print("RAG index built. Publish it with scripts/publish_rag_artifacts.py.")
