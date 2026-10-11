"""
backend/ingest_pdfs.py — Standalone CLI ingestion for AgroSphere's RAG corpus.

Scans backend/data/pdfs/ for PDF documents (e.g. TNAU manual),
extracts text, chunks with RecursiveCharacterTextSplitter (chunk_size=600, chunk_overlap=100),
persists vector embeddings into ChromaDB collection 'agricultural_extension',
tokenizes using regex to preserve hyphenated agronomic terms,
and serializes a BM25Okapi index to backend/data/bm25_index.pkl.
"""

from __future__ import annotations

import argparse
import os
import pickle
import re
import sys
from pathlib import Path
from typing import List, Optional

import chromadb
from rank_bm25 import BM25Okapi

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:
    from langchain.text_splitter import RecursiveCharacterTextSplitter

# Default paths relative to backend directory
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_PDF_DIR = BASE_DIR / "data" / "pdfs"
DEFAULT_CHROMA_DIR = BASE_DIR / ".chroma"
DEFAULT_BM25_PATH = BASE_DIR / "data" / "bm25_index.pkl"
COLLECTION_NAME = "agricultural_extension"

CHUNK_SIZE = 600
CHUNK_OVERLAP = 100


def tokenize(text: str) -> list[str]:
    """Tokenize corpus preserving hyphenated agronomic terms (e.g., 'pre-harvest', 'Alternaria-blight')."""
    return re.findall(r"\b\w+(?:-\w+)*\b", text.lower())


def extract_documents_from_pdfs(pdf_dir: Path):
    """Extract page documents from all PDFs in the given directory."""
    pdf_files = sorted(list(pdf_dir.glob("*.pdf")))
    if not pdf_files:
        return []

    documents = []
    # Prefer PyPDFLoader from langchain_community if available
    try:
        from langchain_community.document_loaders import PyPDFLoader

        for pdf_file in pdf_files:
            print(f"[Extract] Loading PDF: {pdf_file.name} ...")
            loader = PyPDFLoader(str(pdf_file))
            loaded_docs = loader.load()
            print(f"  -> Extracted {len(loaded_docs)} pages from {pdf_file.name}")
            documents.extend(loaded_docs)
    except ImportError:
        from pypdf import PdfReader
        from langchain_core.documents import Document

        for pdf_file in pdf_files:
            print(f"[Extract] Loading PDF via pypdf: {pdf_file.name} ...")
            reader = PdfReader(str(pdf_file))
            loaded_pages = 0
            for page_idx, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                if text.strip():
                    documents.append(
                        Document(
                            page_content=text,
                            metadata={"source": pdf_file.name, "page": page_idx + 1},
                        )
                    )
                    loaded_pages += 1
            print(f"  -> Extracted {loaded_pages} pages from {pdf_file.name}")

    return documents


def ingest_pdfs(
    pdf_dir: Optional[Path] = None,
    chroma_dir: Optional[Path] = None,
    bm25_out: Optional[Path] = None,
) -> None:
    """Core ingestion routine: chunking, ChromaDB embedding persistence, and BM25 index pickling."""
    pdf_dir = Path(pdf_dir) if pdf_dir else DEFAULT_PDF_DIR
    chroma_dir = Path(chroma_dir) if chroma_dir else DEFAULT_CHROMA_DIR
    bm25_out = Path(bm25_out) if bm25_out else DEFAULT_BM25_PATH

    print("=" * 60)
    print("AgroSphere RAG Corpus Ingestion")
    print("=" * 60)
    print(f"PDF Directory:       {pdf_dir}")
    print(f"ChromaDB Directory:  {chroma_dir}")
    print(f"BM25 Output Path:    {bm25_out}")
    print(f"Chunk Size:          {CHUNK_SIZE}")
    print(f"Chunk Overlap:       {CHUNK_OVERLAP}")
    print("=" * 60)

    if not pdf_dir.exists():
        print(f"Error: PDF directory not found at {pdf_dir}", file=sys.stderr)
        sys.exit(1)

    # 1. Extract documents
    raw_docs = extract_documents_from_pdfs(pdf_dir)
    if not raw_docs:
        print(f"No PDF documents found to ingest in {pdf_dir}", file=sys.stderr)
        sys.exit(1)

    # 2. Chunk text
    print(f"[Chunking] Splitting documents (chunk_size={CHUNK_SIZE}, chunk_overlap={CHUNK_OVERLAP})...")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )
    splits = splitter.split_documents(raw_docs)
    total_chunks = len(splits)
    print(f"[Chunking] Successfully generated {total_chunks} chunks.")

    doc_ids: List[str] = [f"doc_{i}" for i in range(total_chunks)]
    doc_texts: List[str] = [doc.page_content for doc in splits]
    doc_metas: List[dict] = [doc.metadata for doc in splits]

    # 3. ChromaDB storage & vector embeddings
    print(f"[ChromaDB] Initializing PersistentClient at '{chroma_dir}'...")
    chroma_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(chroma_dir))

    try:
        client.delete_collection(name=COLLECTION_NAME)
        print(f"[ChromaDB] Cleared previous collection '{COLLECTION_NAME}'.")
    except Exception:
        pass

    collection = client.get_or_create_collection(name=COLLECTION_NAME)
    print(f"[ChromaDB] Writing {total_chunks} chunks into collection '{COLLECTION_NAME}'...")

    batch_size = 250
    for i in range(0, total_chunks, batch_size):
        end_idx = min(i + batch_size, total_chunks)
        collection.add(
            ids=doc_ids[i:end_idx],
            documents=doc_texts[i:end_idx],
            metadatas=doc_metas[i:end_idx],
        )
        print(f"  -> Embedded & stored chunks {i + 1} to {end_idx} of {total_chunks}")

    print(f"[ChromaDB] Finished persisting {collection.count()} chunks.")

    # 4. BM25 Tokenization & Index Creation
    print("[BM25] Tokenizing corpus using regex: r'\\b\\w+(?:-\\w+)*\\b' ...")
    tokenized_corpus = [tokenize(text) for text in doc_texts]

    print("[BM25] Building BM25Okapi index...")
    bm25_index = BM25Okapi(tokenized_corpus)

    bm25_out.parent.mkdir(parents=True, exist_ok=True)
    print(f"[BM25] Pickling BM25 index and metadata to '{bm25_out}'...")
    with open(bm25_out, "wb") as f:
        pickle.dump(
            {
                "bm25": bm25_index,
                "doc_ids": doc_ids,
                "doc_texts": doc_texts,
            },
            f,
        )
    print(f"[BM25] Pickled successfully ({len(doc_ids)} documents serialized).")

    print("=" * 60)
    print("Ingestion completed successfully.")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest PDFs into AgroSphere ChromaDB and BM25 index."
    )
    parser.add_argument(
        "--pdf-dir",
        type=Path,
        default=DEFAULT_PDF_DIR,
        help=f"Directory containing PDF files (default: {DEFAULT_PDF_DIR})",
    )
    parser.add_argument(
        "--chroma-dir",
        type=Path,
        default=DEFAULT_CHROMA_DIR,
        help=f"ChromaDB persistent directory (default: {DEFAULT_CHROMA_DIR})",
    )
    parser.add_argument(
        "--out",
        "--bm25-out",
        dest="bm25_out",
        type=Path,
        default=DEFAULT_BM25_PATH,
        help=f"Path to write pickled BM25 index (default: {DEFAULT_BM25_PATH})",
    )
    args = parser.parse_args()

    ingest_pdfs(
        pdf_dir=args.pdf_dir,
        chroma_dir=args.chroma_dir,
        bm25_out=args.bm25_out,
    )


if __name__ == "__main__":
    main()
