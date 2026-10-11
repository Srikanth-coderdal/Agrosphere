# Patch: `schemas/diagnostic.py` — Add `citations` Field

## Reference implementation
```python
from typing import List, Optional
from pydantic import BaseModel, Field

class VerifiedDiagnosticResponse(BaseModel):
    # ... existing fields (diagnosis, safe_dosages, is_verified, etc.) ...

    citations: List[str] = Field(
        default_factory=list,
        description=(
            "Chunk IDs (e.g. 'doc_42') from the retrieved TNAU context that "
            "support the claims in this response. Every dosage or treatment "
            "claim should trace back to at least one entry here. Empty list "
            "means no claim could be grounded — treat the response as "
            "unverified."
        ),
    )
```

This alone doesn't *enforce* traceability — it just gives you somewhere to
put the chunk IDs collected in `rag_guardrail.py`. The audit's B-3 finding
also notes `is_verified` is currently self-reported by the LLM rather than
independently checked. If you want that closed too (not in the original
P0/P1 scope, but worth flagging): a cheap follow-on check is asserting
`citations` is non-empty whenever `safe_dosages` is non-empty, and
overriding `is_verified = False` server-side if that assertion fails,
rather than trusting the model's own flag.

## Acceptance criteria
- [ ] `citations: List[str]` present on the schema with a sensible default.
- [ ] `rag_guardrail.py` populates it from the chunk IDs actually injected into the prompt (see previous patch).

---

## Antigravity prompt

```
In schemas/diagnostic.py, add a new field to VerifiedDiagnosticResponse:

    citations: List[str] = Field(
        default_factory=list,
        description="Chunk IDs from retrieved TNAU context supporting claims in this response."
    )

Make sure List is imported from typing. Then find every place
VerifiedDiagnosticResponse is constructed (likely in rag_guardrail.py or
main.py) and confirm citations is being populated — if any construction
site doesn't pass it, flag that to me rather than silently defaulting to
empty.
```
