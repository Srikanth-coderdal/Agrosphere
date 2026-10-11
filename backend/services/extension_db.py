import asyncio
import math
import os
import logging
import pickle
import re
from typing import Optional, List, Tuple
import chromadb
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROMA_PATH = os.path.join(BASE_DIR, ".chroma")
PDF_DIR = os.path.join(BASE_DIR, "data", "pdfs")
BM25_PICKLE_PATH = os.path.join(BASE_DIR, "data", "bm25_index.pkl")

_client = chromadb.PersistentClient(path=CHROMA_PATH)
_collection_name = "agricultural_extension"

# In-memory BM25 cache — rebuilt lazily, invalidated whenever ingest_pdfs() runs
_bm25_index = None
_bm25_ids: List[str] = []
_bm25_corpus: List[str] = []

# Cross-encoder reranker — loaded lazily on first use so app startup/imports
# stay fast when no query has been made yet (model load takes a couple seconds).
_reranker = None
RERANK_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _tokenize(text: str) -> List[str]:
    """Tokenize corpus preserving hyphenated agronomic terms (e.g. pre-harvest, Alternaria-blight)."""
    return re.findall(r"\b\w+(?:-\w+)*\b", text.lower())


def _get_reranker():
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder
        logger.info(f"Loading cross-encoder reranker: {RERANK_MODEL_NAME}")
        _reranker = CrossEncoder(RERANK_MODEL_NAME)
    return _reranker


def get_chroma_collection():
    return _client.get_or_create_collection(name=_collection_name)


def _reset_bm25_cache():
    global _bm25_index, _bm25_ids, _bm25_corpus
    _bm25_index = None
    _bm25_ids = []
    _bm25_corpus = []


def _get_bm25_index():
    """Return cached BM25 index, deserialize from disk pickle if available, or fall back to ChromaDB scan."""
    global _bm25_index, _bm25_ids, _bm25_corpus
    if _bm25_index is not None:
        return _bm25_index, _bm25_ids

    if os.path.exists(BM25_PICKLE_PATH):
        logger.info(f"Loading BM25 index from {BM25_PICKLE_PATH}")
        try:
            with open(BM25_PICKLE_PATH, "rb") as f:
                data = pickle.load(f)
            _bm25_index = data["bm25"]
            _bm25_ids = data["doc_ids"]
            _bm25_corpus = data["doc_texts"]
            return _bm25_index, _bm25_ids
        except Exception as e:
            logger.warning(f"Failed to load BM25 pickle ({e}); falling back to ChromaDB scan.")

    logger.warning(
        f"BM25 index pickle not found at {BM25_PICKLE_PATH}. "
        "Falling back to ChromaDB scan. Run 'python backend/ingest_pdfs.py' to prebuild the index."
    )
    collection = get_chroma_collection()
    data = collection.get()
    _bm25_ids = data["ids"]
    _bm25_corpus = data["documents"]
    tokenized_corpus = [_tokenize(doc) for doc in _bm25_corpus]
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


def hybrid_retrieval(query_text: str, pool_size: int = 15, rerank_pool: int = 10) -> List[str]:
    """Combine dense (ChromaDB) and sparse (BM25) retrieval via RRF.
    pool_size controls how many candidates each method contributes before fusion.
    Returns the top `rerank_pool` fused ids — a candidate pool for the cross-encoder
    to rescore, NOT the final answer set. Keep rerank_pool well above the eventual
    final_k, or the reranker has nothing meaningful to choose between."""
    collection = get_chroma_collection()
    if collection.count() == 0:
        return []

    dense_results = collection.query(query_texts=[query_text], n_results=pool_size)
    dense_ids = dense_results["ids"][0] if dense_results.get("ids") else []

    bm25_index, bm25_ids = _get_bm25_index()
    sparse_ids: List[str] = []
    if bm25_index is not None:
        tokenized_query = _tokenize(query_text)
        scores = bm25_index.get_scores(tokenized_query)
        ranked = sorted(zip(bm25_ids, scores), key=lambda x: x[1], reverse=True)[:pool_size]
        sparse_ids = [doc_id for doc_id, _ in ranked]

    return _reciprocal_rank_fusion([dense_ids, sparse_ids])[:rerank_pool]


async def rerank_chunks(query_text: str, doc_ids: List[str], doc_texts: List[str], final_k: int = 3) -> List[Tuple[str, str, float]]:
    """Rescore fused candidates with a cross-encoder that scores the query against
    each chunk jointly (unlike BM25/vector similarity, which score independently).
    This is what actually cleans up cases where RRF surfaces a keyword/vector hit
    that turns out to be a noisy or off-topic chunk on closer reading.
    Returns (doc_id, doc_text, score) tuples, highest score first, length <= final_k."""
    if not doc_ids:
        return []

    reranker = _get_reranker()
    pairs = [[query_text, text] for text in doc_texts]
    loop = asyncio.get_event_loop()
    raw_scores = await loop.run_in_executor(None, reranker.predict, pairs)

    scores = [_sigmoid(float(s)) for s in raw_scores]
    ranked = sorted(zip(doc_ids, doc_texts, scores), key=lambda x: x[2], reverse=True)
    return ranked[:final_k]


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

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=600, chunk_overlap=100)
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


async def query_extension_context(crop_type: str, farmer_comment: Optional[str] = None, n_results: int = 3) -> str:
    """Retrieve matching chunks for a given crop type (+ optional farmer comment) using
    hybrid retrieval (BM25 + vector, fused via RRF) followed by cross-encoder reranking."""
    results = await query_extension_context_scored(crop_type, farmer_comment=farmer_comment, n_results=n_results)
    if not results:
        return ""
    return "\n\n---\n\n".join(text for _id, text, _score in results)


async def query_extension_context_scored(
    crop_type: str, farmer_comment: Optional[str] = None, n_results: int = 3, rerank_pool: int = 10
) -> List[Tuple[str, str, float]]:
    """Same retrieval as query_extension_context, but also returns cross-encoder
    scores per chunk. Callers that need confidence-based refusal logic (Pillar B)
    should use this instead of the plain string version."""
    collection = get_chroma_collection()
    if collection.count() == 0:
        return []

    query_text = crop_type if not farmer_comment else f"{crop_type} {farmer_comment}"

    fused_ids = hybrid_retrieval(query_text, pool_size=15, rerank_pool=rerank_pool)
    if not fused_ids:
        return []

    fetched = collection.get(ids=fused_ids)
    id_to_doc = dict(zip(fetched["ids"], fetched["documents"]))
    ordered_ids = [i for i in fused_ids if i in id_to_doc]
    ordered_docs = [id_to_doc[i] for i in ordered_ids]

    return await rerank_chunks(query_text, ordered_ids, ordered_docs, final_k=n_results)
