from pathlib import Path

import fsspec

from config import RAG_ARTIFACT_URI, RAG_ARTIFACT_VERSION, RAG_CACHE_DIR, local_rag_paths

ARTIFACT_FILENAMES = ("FSoft_HR.pdf", "index.faiss", "index.pkl", "metadata.json")


def get_rag_artifact_paths() -> tuple[Path, Path]:
    """Return local paths after lazily materializing a versioned remote RAG artifact."""
    if not RAG_ARTIFACT_URI:
        return local_rag_paths()
    if not RAG_ARTIFACT_VERSION:
        raise RuntimeError("RAG_ARTIFACT_VERSION is required when RAG_ARTIFACT_URI is configured")

    cache_dir = Path(RAG_CACHE_DIR) / RAG_ARTIFACT_VERSION
    pdf_path = cache_dir / "FSoft_HR.pdf"
    index_path = cache_dir / "index"
    required = (pdf_path, index_path / "index.faiss", index_path / "index.pkl")
    if all(path.exists() for path in required):
        return pdf_path, index_path

    filesystem, base_path = fsspec.core.url_to_fs(RAG_ARTIFACT_URI)
    version_path = f"{base_path.rstrip('/')}/{RAG_ARTIFACT_VERSION}"
    cache_dir.mkdir(parents=True, exist_ok=True)
    index_path.mkdir(parents=True, exist_ok=True)
    destinations = {
        "FSoft_HR.pdf": pdf_path,
        "index.faiss": index_path / "index.faiss",
        "index.pkl": index_path / "index.pkl",
        "metadata.json": cache_dir / "metadata.json",
    }
    for filename, destination in destinations.items():
        source = f"{version_path}/{filename}"
        if filename == "metadata.json" and not filesystem.exists(source):
            continue
        if not filesystem.exists(source):
            raise RuntimeError(f"RAG artifact is missing required file: {source}")
        filesystem.get(source, str(destination))
    return pdf_path, index_path
