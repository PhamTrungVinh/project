"""Publish the HR PDF and FAISS index as an immutable versioned object-store artifact."""
import argparse
import hashlib
import json
from pathlib import Path

import fsspec


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", required=True, help="Object-store base URI, e.g. s3://bucket/rag")
    parser.add_argument("--version", required=True)
    parser.add_argument("--pdf", default="FSoft_HR.pdf")
    parser.add_argument("--index-dir", default="faiss_index")
    args = parser.parse_args()
    if "/" in args.version or "\\" in args.version:
        raise SystemExit("Version must be a single identifier")
    files = {"FSoft_HR.pdf": Path(args.pdf), "index.faiss": Path(args.index_dir) / "index.faiss", "index.pkl": Path(args.index_dir) / "index.pkl"}
    for path in files.values():
        if not path.is_file():
            raise SystemExit(f"Missing artifact: {path}")
    filesystem, base_path = fsspec.core.url_to_fs(args.destination)
    version_path = f"{base_path.rstrip('/')}/{args.version}"
    if filesystem.exists(version_path):
        raise SystemExit(f"Refusing to overwrite immutable artifact version: {args.version}")
    filesystem.makedirs(version_path, exist_ok=False)
    for name, source in files.items():
        filesystem.put(str(source), f"{version_path}/{name}")
    metadata = {"version": args.version, "files": {name: {"sha256": sha256(path), "bytes": path.stat().st_size} for name, path in files.items()}}
    with filesystem.open(f"{version_path}/metadata.json", "w") as handle:
        json.dump(metadata, handle, sort_keys=True)
    print(f"Published RAG artifact version {args.version}")


if __name__ == "__main__":
    main()
