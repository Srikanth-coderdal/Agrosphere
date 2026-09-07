import os
import logging
from typing import Optional, List
import chromadb
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROMA_PATH = os.path.join(BASE_DIR, ".chroma")
PDF_DIR = os.path.join(BASE_DIR, "data", "pdfs")

_client = chromadb.PersistentClient(path=CHROMA_PATH)
_collection_name = "agricultural_extension"

# In-memory BM25 cache — rebuilt lazily, invalidated whenever ingest_pdfs() runs
_bm25_index = None
_bm25_ids: List[str] = []
_bm25_corpus: List[str] = []


def get_chroma_collection():
    return _client.get_or_create_collection(name=_collection_name)


def _reset_bm25_cache():
    global _bm25_index, _bm25_ids, _bm25_corpus
    _bm25_index = None
    _bm25_ids = []
    _bm25_corpus = []


def _get_bm25_index():
    """Build (or return cached) BM25 index over the full ChromaDB corpus."""
    global _bm25_index, _bm25_ids, _bm25_corpus
    if _bm25_index is None:
        collection = get_chroma_collection()
        data = collection.get()
        _bm25_ids = data["ids"]
        _bm25_corpus = data["documents"]
        tokenized_corpus = [doc.lower().split() for doc in _bm25_corpus]
        _bm25_index = BM25Okapi(tokenized_corpus) if tokenized_corpus else None
    return _bm25_index, _bm25_ids


def _reciprocal_rank_fusion(rankings: List[List[str]], k: int = 60) -> List[str]:
    """Merge multiple ranked ID lists via Reciprocal Rank Fusion.
    Documents appearing near the top of multiple rankings score highest."""
    scores = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.keys(), key=lambda d: scores[d], reverse=True)


def hybrid_retrieval(query_text: str, pool_size: int = 15, final_k: int = 3) -> List[str]:
    """Combine dense (ChromaDB) and sparse (BM25) retrieval via RRF.
    pool_size controls how many candidates each method contributes before fusion —
    keep this well above final_k, or RRF has nothing meaningful to re-rank."""
    collection = get_chroma_collection()
    if collection.count() == 0:
        return []

    dense_results = collection.query(query_texts=[query_text], n_results=pool_size)
    dense_ids = dense_results["ids"][0] if dense_results.get("ids") else []

    bm25_index, bm25_ids = _get_bm25_index()
    sparse_ids: List[str] = []
    if bm25_index is not None:
        tokenized_query = query_text.lower().split()
        scores = bm25_index.get_scores(tokenized_query)
        ranked = sorted(zip(bm25_ids, scores), key=lambda x: x[1], reverse=True)[:pool_size]
        sparse_ids = [doc_id for doc_id, _ in ranked]

    return _reciprocal_rank_fusion([dense_ids, sparse_ids])[:final_k]


def ingest_pdfs():
    """Load PDFs from data/pdfs/, chunk them, and store in ChromaDB."""
    os.makedirs(PDF_DIR, exist_ok=True)
    collection = get_chroma_collection()

    docs = []
    for filename in os.listdir(PDF_DIR):
        if filename.endswith(".pdf"):
            logger.info(f"Loading {filename}")
            loader = PyPDFLoader(os.path.join(PDF_DIR, filename))
            docs.extend(loader.load())

    if not docs:
        logger.info("No PDFs found to ingest.")
        return

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    splits = text_splitter.split_documents(docs)

    texts = [doc.page_content for doc in splits]
    metadatas = [doc.metadata for doc in splits]
    ids = [f"doc_{i}" for i in range(len(splits))]

    try:
        _client.delete_collection(name=_collection_name)
    except Exception:
        pass
    collection = get_chroma_collection()

    collection.add(documents=texts, metadatas=metadatas, ids=ids)
    _reset_bm25_cache()  # old ids/corpus are stale after a re-ingest
    logger.info(f"Ingested {len(splits)} chunks into ChromaDB.")


def query_extension_context(crop_type: str, farmer_comment: Optional[str] = None, n_results: int = 3) -> str:
    """Retrieve matching chunks for a given crop type (+ optional farmer comment) using hybrid retrieval."""
    collection = get_chroma_collection()
    if collection.count() == 0:
        return ""

    query_text = crop_type if not farmer_comment else f"{crop_type} {farmer_comment}"

    fused_ids = hybrid_retrieval(query_text, pool_size=15, final_k=n_results)
    if not fused_ids:
        return ""

    fetched = collection.get(ids=fused_ids)
    id_to_doc = dict(zip(fetched["ids"], fetched["documents"]))
    ordered_docs = [id_to_doc[i] for i in fused_ids if i in id_to_doc]

    return "\n\n---\n\n".join(ordered_docs)
