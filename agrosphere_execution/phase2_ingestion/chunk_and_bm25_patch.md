# Patch: Chunk Size, BM25 Pickle Loading, Tokenizer

`ingest_pdfs.py` (new file, see sibling) handles the *offline* build and
pickling of the BM25 index. This patch covers the *runtime* side in
`extension_db.py` — it needs to load that pickle instead of rebuilding
from a full `collection.get()` scan on every process start.

## 1. Chunk size correction — ~L130
**Current:**
```python
text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
```
**Fixed:**
```python
text_splitter = RecursiveCharacterTextSplitter(chunk_size=600, chunk_overlap=100)
```
If this splitter is defined in more than one place (e.g. duplicated
between the in-module `ingest_pdfs()` function and elsewhere), fix all
occurrences — and consider deleting the in-module version once the
standalone script replaces it, so there's only one source of truth for
chunking parameters.

## 2. BM25 load-from-pickle at startup (`_get_bm25_index()`, ~L55)
**Current (rebuilds from full ChromaDB scan every time):**
```python
def _get_bm25_index():
    global _bm25_corpus, _bm25_index
    if _bm25_index is None:
        docs = collection.get()  # full scan
        _bm25_corpus = docs["documents"]
        tokenized_corpus = [doc.lower().split() for doc in _bm25_corpus]
        _bm25_index = BM25Okapi(tokenized_corpus)
    return _bm25_index
```
**Reference implementation:**
```python
import pickle
from pathlib import Path

BM25_PICKLE_PATH = Path("data/bm25_index.pkl")

def _get_bm25_index():
    global _bm25_corpus, _bm25_doc_ids, _bm25_index
    if _bm25_index is not None:
        return _bm25_index

    if BM25_PICKLE_PATH.exists():
        with open(BM25_PICKLE_PATH, "rb") as f:
            data = pickle.load(f)
        _bm25_index = data["bm25"]
        _bm25_doc_ids = data["doc_ids"]
        _bm25_corpus = data["doc_texts"]
        return _bm25_index

    # Fallback: no pickle yet (fresh env) — rebuild once from Chroma, same as before
    docs = collection.get()
    _bm25_corpus = docs["documents"]
    _bm25_doc_ids = docs["ids"]
    tokenized_corpus = [_tokenize(doc) for doc in _bm25_corpus]
    _bm25_index = BM25Okapi(tokenized_corpus)
    return _bm25_index
```
Note the fallback branch keeps things working before you've run
`ingest_pdfs.py` for the first time in a given environment — but it means
the pickle and the live ChromaDB collection can drift out of sync if
someone re-ingests without also re-running the standalone script. Worth a
one-line comment or a startup log warning if `BM25_PICKLE_PATH` doesn't
exist, so that's not silent.

## 3. Tokenizer upgrade
**Current:**
```python
tokenized_corpus = [doc.lower().split() for doc in _bm25_corpus]
```
**Fixed** (regex-based, keeps hyphenated terms like `pre-harvest` intact):
```python
import re

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*")

def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]
```
Use `_tokenize()` everywhere `doc.lower().split()` currently appears,
including inside `ingest_pdfs.py` — the same tokenizer must be used at
index-build time and query time, or BM25 scores drift. (`ingest_pdfs.py`
in this package already uses the regex version — this is the matching
runtime-side fix.)

## Acceptance criteria
- [ ] Chunking uses 600/100 everywhere, not 1000/200.
- [ ] Server startup loads `data/bm25_index.pkl` if present instead of scanning ChromaDB.
- [ ] Tokenizer is identical (same regex) at both ingest time and query time.
- [ ] `pre-harvest`, `Alternaria-blight` etc. survive tokenization as single tokens — spot-check with `_tokenize("pre-harvest interval")`.

---

## Antigravity prompt

```
In backend/services/extension_db.py:

1. Find every RecursiveCharacterTextSplitter(chunk_size=1000,
   chunk_overlap=200) and change it to chunk_size=600, chunk_overlap=100.

2. In _get_bm25_index() (or equivalent), change it to first try loading a
   pickled BM25 index from data/bm25_index.pkl (pickle.load, expects a dict
   with keys "bm25", "doc_ids", "doc_texts") before falling back to the
   existing full collection.get() rebuild. Only rebuild from Chroma if the
   pickle file doesn't exist.

3. Replace every `doc.lower().split()` tokenization call with a shared
   _tokenize() helper using regex `[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*` so
   hyphenated terms like "pre-harvest" aren't split. Make sure this same
   tokenizer is used consistently at query time (wherever the query string
   is tokenized for BM25 lookup) — not just at corpus-build time.

I've already got a standalone backend/ingest_pdfs.py that builds and
pickles this index offline with the same tokenizer — don't duplicate that
logic, just make the runtime loader consume its output.

Show me the diff before applying.
```
