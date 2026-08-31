import os
import logging
from typing import Optional, List
import chromadb
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROMA_PATH = os.path.join(BASE_DIR, ".chroma")
PDF_DIR = os.path.join(BASE_DIR, "data", "pdfs")

_client = chromadb.PersistentClient(path=CHROMA_PATH)
_collection_name = "agricultural_extension"

def get_chroma_collection():
    return _client.get_or_create_collection(name=_collection_name)

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
    
    # We clear the collection first for idempotency in this demo
    try:
        _client.delete_collection(name=_collection_name)
    except Exception:
        pass
    collection = get_chroma_collection()

    collection.add(
        documents=texts,
        metadatas=metadatas,
        ids=ids
    )
    logger.info(f"Ingested {len(splits)} chunks into ChromaDB.")

def query_extension_context(crop_type: str, n_results: int = 3) -> str:
    """Retrieve matching chunks for a given crop type from ChromaDB."""
    collection = get_chroma_collection()
    if collection.count() == 0:
        return ""
    
    results = collection.query(
        query_texts=[crop_type],
        n_results=n_results
    )
    
    if not results or not results["documents"] or not results["documents"][0]:
        return ""
        
    return "\n\n---\n\n".join(results["documents"][0])
