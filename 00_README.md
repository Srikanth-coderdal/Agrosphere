# AgroSphere — Execution Package (Audit → 100%)

This package operationalizes the RAG audit dated 2026-09-07. It's built so you
can either apply patches by hand, or feed each task block below straight to
**Google Antigravity's agent** — it has your real repo open, so it can locate
the exact surrounding code and apply the diff correctly. I don't have your
source files, only the audit's quoted excerpts, so treat the "Reference
Implementation" snippets as ground truth for *intent*, and let Antigravity
match them against your actual `extension_db.py` / `rag_guardrail.py` /
`main.py`.

## How to drive this with Antigravity

For each task below:
1. Open the target file in Antigravity.
2. Paste the "Antigravity prompt" block into the agent chat.
3. Review the diff before accepting — especially Phase 1, since it's
   safety-critical (refusal gating, dosage citation).
4. Run your test suite / a manual `/api/scan` smoke test after each P0 item.

Work strictly in phase order. Phase 2 and 3 depend on Phase 1's
`query_extension_context_scored()` path being the one actually wired into
the guardrail — building the eval harness before that's fixed means you'd be
CI-gating a pipeline that isn't the one in production.

## Files in this package

| File | Purpose |
|---|---|
| `phase1_patches/extension_db_patch.md` | Async unblock + sigmoid normalization |
| `phase1_patches/rag_guardrail_patch.md` | Refusal gate + citation-tagged context |
| `phase1_patches/schemas_diagnostic_patch.md` | `citations: List[str]` field |
| `phase2_ingestion/ingest_pdfs.py` | Standalone CLI ingestion script (new file) |
| `phase2_ingestion/chunk_and_bm25_patch.md` | Chunk size fix + BM25 pickle + tokenizer |
| `phase3_eval/eval_dataset.json` | Golden QA dataset **template** (see warning below) |
| `phase3_eval/eval_rag.py` | Ragas evaluation script (new file) |
| `phase3_eval/rag_eval.yml` | GitHub Actions workflow (new file, → `.github/workflows/`) |
| `phase3_eval/weather_timeout_patch.md` | httpx timeout fix |

## ⚠️ On `eval_dataset.json`

I did **not** fabricate real Mancozeb/fungicide dosage numbers for the
sample entries — inventing agronomic dosage data and presenting it as a
verified golden answer would recreate exactly the hallucination risk this
audit is trying to close. The template has the correct schema and a few
structurally-complete placeholder entries clearly marked
`"REPLACE_WITH_VERIFIED_TNAU_TEXT"`. You (or a domain reviewer) need to
fill these from the actual TNAU PDF — that manual verification step is the
entire point of a golden set; an LLM-generated one (mine included) defeats
its purpose, as the audit itself notes.

## Priority order (from the audit)

| Priority | Item | Effort |
|---|---|---|
| 🔴 P0 | Wrap `reranker.predict()` in `run_in_executor` | 30 min |
| 🔴 P0 | Point `rag_guardrail.py` at `query_extension_context_scored()` | 15 min |
| 🔴 P0 | Sigmoid normalize + `is_refusal < 0.35` gate | 30 min |
| 🔴 P0 | `[chunk_id]` citation tags + prompt instruction | 20 min |
| 🟠 P1 | Chunk size 1000/200 → 600/100 | 10 min |
| 🟠 P1 | Standalone `ingest_pdfs.py` + BM25 pickle | 45 min |
| 🟠 P1 | `citations: List[str]` on `VerifiedDiagnosticResponse` | 10 min |
| 🟡 P2 | `tests/eval_dataset.json` (50+ verified pairs) | 2–4 hrs (manual) |
| 🟡 P2 | `eval_rag.py` with Ragas | 1 hr |
| 🟡 P2 | `.github/workflows/rag_eval.yml` | 30 min |
| 🟢 P3 | Regex/NLTK BM25 tokenization | 30 min |
| 🟢 P3 | `httpx` timeout on `/api/weather` | 5 min |
