# Patch: `extension_db.py` — Async Unblocking + Sigmoid Normalization

## 1. Async unblock (`rerank_chunks()`, ~L108)

**Current (blocking):**
```python
reranker = _get_reranker()
pairs = [[query_text, text] for text in doc_texts]
scores = reranker.predict(pairs)
ranked = sorted(zip(doc_ids, doc_texts, scores), key=lambda x: x[2], reverse=True)
```

**Reference implementation:**
```python
import asyncio

async def rerank_chunks(query_text: str, doc_ids: list[str], doc_texts: list[str]):
    reranker = _get_reranker()
    pairs = [[query_text, text] for text in doc_texts]

    loop = asyncio.get_event_loop()
    raw_scores = await loop.run_in_executor(None, reranker.predict, pairs)

    scores = [_sigmoid(s) for s in raw_scores]  # see part 2 below
    ranked = sorted(zip(doc_ids, doc_texts, scores), key=lambda x: x[2], reverse=True)
    return ranked
```

Note: this makes `rerank_chunks` a coroutine. Every caller
(`query_extension_context_scored`, `query_extension_context`) needs `await`
added, and their own callers need to be `async def` up the chain to
`rag_guardrail.py`. FastAPI route handlers are already `async def`, so this
should just be a matter of threading `await` through, not restructuring.

## 2. Sigmoid normalization

Add once near the top of the module:
```python
import math

def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))
```

Apply it to raw cross-encoder logits **before** they leave
`rerank_chunks()` (folded into the snippet above), so every downstream
consumer — including `query_extension_context_scored()` — always receives
scores bounded in `[0.0, 1.0]`. Do not normalize a second time downstream.

## Acceptance criteria
- [ ] `reranker.predict()` no longer runs on the event loop thread directly.
- [ ] All scores returned by `rerank_chunks()` / `query_extension_context_scored()` are in `[0.0, 1.0]`.
- [ ] 10-pair rerank no longer blocks other concurrent `/api/*` requests (verify with a concurrent load test or `asyncio` debug mode).

---

## Antigravity prompt

```
In backend/services/extension_db.py:

1. Find the function that calls reranker.predict(pairs) synchronously
   (currently inside rerank_chunks, around the cross-encoder reranking
   logic). Wrap that call in
   `await asyncio.get_event_loop().run_in_executor(None, reranker.predict, pairs)`
   and make the function async. Update every call site up the chain
   (query_extension_context_scored, query_extension_context, and their
   callers in rag_guardrail.py / main.py) to be async and to await this
   call — do not leave a sync/async mismatch.

2. Add a module-level `_sigmoid(x: float) -> float` helper using
   `1.0 / (1.0 + math.exp(-x))` (import math). Apply it to every raw score
   coming out of reranker.predict() before it's returned from
   rerank_chunks(), so all downstream scores are bounded in [0.0, 1.0].
   Do not apply sigmoid a second time in any downstream function.

Show me the diff before applying.
```
