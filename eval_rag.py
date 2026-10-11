from ragas.run_config import RunConfig
"""
eval_rag.py — Offline Ragas evaluation script for AgroSphere's RAG pipeline.

Evaluates retrieval quality against ground truth baselines.
Exits with 1 if any metric fails to meet the threshold, or 0 if all pass.
"""

import asyncio
import json
import math
import sys
from pathlib import Path

from datasets import Dataset
from ragas import evaluate
from ragas.metrics import answer_relevancy, context_precision, faithfulness

# Ensure repository root is in sys.path for backend package imports
REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv
_BACKEND_ENV = REPO_ROOT / "backend" / ".env"
if _BACKEND_ENV.exists():
    load_dotenv(dotenv_path=_BACKEND_ENV)
else:
    load_dotenv()

from backend.services.extension_db import query_extension_context_scored

# Evaluation thresholds
THRESHOLDS = {
    "faithfulness": 0.75,
    "answer_relevancy": 0.70,
    "context_precision": 0.65,
}

REFUSAL_THRESHOLD = 0.35
DATASET_PATH = REPO_ROOT / "tests" / "eval_dataset.json"


def load_dataset(path: Path) -> list[dict]:
    """Load evaluation samples from the JSON dataset file."""
    if not path.exists():
        print(f"ERROR: Dataset file not found at {path}")
        sys.exit(1)

    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    # Filter out empty entries or unfilled templates if any
    valid_entries = [
        entry for entry in data if "REPLACE_WITH" not in json.dumps(entry)
    ]
    return valid_entries


async def run_pipeline_for_question(question: str) -> dict:
    """
    Run retrieval for a given question using query_extension_context_scored.
    Returns refusal status, retrieved contexts, and answer representation.
    """
    scored_chunks = await query_extension_context_scored(crop_type=question, n_results=3)

    top_score = scored_chunks[0][2] if scored_chunks else 0.0

    if not scored_chunks or top_score < REFUSAL_THRESHOLD:
        return {
            "is_refusal": True,
            "top_score": top_score,
            "contexts": [],
            "answer": "I cannot provide a verified answer for this query based on available agronomic sources.",
        }

    contexts = [chunk[1] for chunk in scored_chunks]
    context_str = "\n\n---\n\n".join(f"[{cid}] {text}" for cid, text, _ in scored_chunks)

    return {
        "is_refusal": False,
        "top_score": top_score,
        "contexts": contexts,
        "answer": context_str,
    }


async def main() -> None:
    print(f"Loading evaluation dataset from {DATASET_PATH}...")
    dataset = load_dataset(DATASET_PATH)

    if not dataset:
        print("ERROR: Evaluation dataset contains no valid entries.")
        sys.exit(1)

    print(f"Evaluating {len(dataset)} question(s)...")

    questions = []
    answers = []
    contexts = []
    ground_truths = []

    for item in dataset:
        q = item.get("question", "")
        gt = item.get("ground_truth", "")

        result = await run_pipeline_for_question(q)

        if result["is_refusal"]:
            print(f"  [REFUSAL] Score: {result['top_score']:.4f} (< {REFUSAL_THRESHOLD}) | Query: {q[:60]}...")
            continue

        questions.append(q)
        answers.append(result["answer"])
        contexts.append(result["contexts"])
        ground_truths.append(gt)

    if not questions:
        print("ERROR: All queries resulted in refusals. No non-refusal samples available to evaluate.")
        sys.exit(1)

    eval_data = Dataset.from_dict({
        "question": questions,
        "answer": answers,
        "contexts": contexts,
        "ground_truth": ground_truths,
    })

    from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
    from ragas.llms import LangchainLLMWrapper
    from ragas.embeddings import LangchainEmbeddingsWrapper
    import os

    eval_llm = LangchainLLMWrapper(ChatGoogleGenerativeAI(model="gemini-3.6-flash", google_api_key=os.getenv("GEMINI_API_KEY")))
    eval_embeddings = LangchainEmbeddingsWrapper(GoogleGenerativeAIEmbeddings(model="models/text-embedding-004", google_api_key=os.getenv("GEMINI_API_KEY")))

    results = evaluate(
        eval_data,
        metrics=[faithfulness, answer_relevancy, context_precision],
        run_config=RunConfig(max_workers=1, timeout=300),
        llm=eval_llm,
        embeddings=eval_embeddings
    )

    # Display scorecard
    print("\n" + "=" * 65)
    print(f"{'RAGAS EVALUATION SCORECARD':^65}")
    print("=" * 65)
    print(f"{'Metric':<25} | {'Score':<10} | {'Threshold':<10} | {'Status':<8}")
    print("-" * 65)

    failed = False
    for metric_name, threshold in THRESHOLDS.items():
        score = dict(results).get(metric_name, float("nan"))
        is_pass = not math.isnan(score) and score >= threshold
        status_str = "PASS" if is_pass else "FAIL"
        score_str = f"{score:.4f}" if not math.isnan(score) else "NaN"

        print(f"{metric_name:<25} | {score_str:<10} | {threshold:<10.2f} | {status_str:<8}")
        if not is_pass:
            failed = True

    print("=" * 65)

    if failed:
        print("\nCI GATE FAILED: One or more metrics fell below the required threshold.")
        sys.exit(1)
    else:
        print("\nCI GATE PASSED: All metrics met or exceeded the required thresholds.")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
