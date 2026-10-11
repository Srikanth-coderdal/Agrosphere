# Patch: `rag_guardrail.py` — Hard Refusal Gate + Citation Traceability

## Current (wrong function, no gate, no chunk IDs) — ~L79
```python
context = query_extension_context(crop_type, farmer_comment=farmer_comment)
# ... always proceeds to Gemini, no matter how irrelevant context is
prompt += f"\nExtension Context:\n{context if context else 'No specific context found...'}\n"
```

## Reference implementation
```python
import math
from fastapi import HTTPException
from services.extension_db import query_extension_context_scored  # ← switch import

REFUSAL_THRESHOLD = 0.35

async def apply_guardrail(crop_type: str, farmer_comment: str, ...) -> VerifiedDiagnosticResponse:
    # Step 1: scored retrieval (scores already sigmoid-normalized upstream —
    # see extension_db_patch.md; do NOT re-normalize here)
    scored_chunks = await query_extension_context_scored(
        crop_type, farmer_comment=farmer_comment, n_results=3
    )

    # Step 2: hard refusal gate — BEFORE any Gemini call
    top_score = scored_chunks[0][2] if scored_chunks else 0.0
    if not scored_chunks or top_score < REFUSAL_THRESHOLD:
        raise HTTPException(
            status_code=422,
            detail={
                "is_refusal": True,
                "reason": "No sufficiently relevant agronomic context found for this query.",
                "top_relevance_score": top_score,
            },
        )

    # Step 3: build citation-tagged context
    context = "\n\n---\n\n".join(
        f"[{chunk_id}] {text}" for chunk_id, text, _ in scored_chunks
    )
    citation_ids = [chunk_id for chunk_id, _, _ in scored_chunks]

    # Step 4: prompt instructs the model to cite
    prompt = f"{system_prompt}\n\n"
    prompt += (
        "CITATION RULE: Every treatment, dosage, or diagnostic claim must "
        "cite its source chunk in square brackets, e.g. [doc_42]. If a claim "
        "cannot be tied to a chunk ID below, do not state it.\n\n"
    )
    prompt += f"Extension Context:\n{context}\n"

    # ... call Gemini, then populate response.citations = citation_ids
    # (see schemas_diagnostic_patch.md)
```

## Important correction vs. the audit's own draft
The audit's Step 5 code re-applies sigmoid inside `rag_guardrail.py`. If
you've already done the sigmoid patch in `extension_db.py` (Phase 1, item
1), **don't normalize twice** — `scored_chunks` already arrives bounded in
`[0.0, 1.0]`. Pick exactly one location for the sigmoid call; upstream in
`extension_db.py` is the right place since every consumer benefits, not
just the guardrail.

## Acceptance criteria
- [ ] `rag_guardrail.py` imports and calls `query_extension_context_scored`, not `query_extension_context`.
- [ ] Gemini is never called when `top_score < 0.35`; a 422 with `is_refusal: true` is returned instead.
- [ ] Injected context has `[chunk_id]` prefixes on every chunk.
- [ ] Prompt explicitly instructs citation behavior.
- [ ] Manual test: a query with no relevant TNAU content (e.g. "what's the weather forecast for Mars") returns the refusal payload, not a Gemini-generated answer.

---

## Antigravity prompt

```
In backend/services/rag_guardrail.py:

1. Change the import from query_extension_context to
   query_extension_context_scored (from services.extension_db). Update the
   call site to use the scored variant and await it (it's now async per
   the extension_db.py patch).

2. Immediately after retrieval, add a hard refusal gate: if the list of
   scored chunks is empty OR the top chunk's score is below 0.35, raise
   HTTPException(status_code=422, detail={"is_refusal": True, "reason":
   "No sufficiently relevant agronomic context found for this query.",
   "top_relevance_score": <top_score>}) and do NOT proceed to the Gemini
   call. This must short-circuit before any LLM API call is made.

3. Do not re-apply a sigmoid here if extension_db.py already normalizes
   scores upstream — check for double-normalization.

4. When building the context string injected into the prompt, prefix each
   chunk with its [chunk_id] in square brackets, joined by "\n\n---\n\n".
   Add an explicit instruction line to the prompt telling the model to cite
   chunk IDs in brackets for every dosage/treatment claim, and to omit any
   claim it can't tie to a chunk ID.

5. Collect the list of chunk_ids used and set it on the response object's
   new `citations` field (added to VerifiedDiagnosticResponse separately).

Show me the diff before applying, and flag anywhere the existing
apply_guardrail() signature or callers would need to change.
```
