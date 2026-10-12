import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.rag_guardrail import _sanitize_and_ground_llm_result  # noqa: E402

MANUAL = "Spray mancozeb 2.5 g per litre of water. Pre-harvest interval is 7 days."
CHUNKS = [("doc_1", MANUAL, 0.9)]


def run(dosages):
    raw = {
        "pathogen": "Test pathogen",
        "verified_treatment": "Spray as per manual.",
        "confidence": 0.9,
        "safe_dosages": dosages,
    }
    result = _sanitize_and_ground_llm_result(raw, CHUNKS, ["doc_1"], None, "gemini", False)
    return result.safe_dosages


def make(name, dose, phi):
    return {
        "chemical_name": name,
        "dosage": dose,
        "unit": "g/l",
        "max_frequency": "once",
        "pre_harvest_interval_days": phi,
    }


def test_invented_dosage_number_is_replaced():
    out = run([make("mancozeb", "9", 7)])
    assert len(out) == 1
    assert "confirm" in out[0].dosage.lower()


def test_dosage_from_manual_is_kept():
    out = run([make("mancozeb", "2.5", 7)])
    assert out[0].dosage == "2.5"


def test_invented_phi_is_removed_and_real_phi_is_kept():
    wrong = run([make("mancozeb", "2.5", 21)])
    right = run([make("mancozeb", "2.5", 7)])
    assert wrong[0].pre_harvest_interval_days is None
    assert right[0].pre_harvest_interval_days == 7


def test_chemical_not_in_manual_is_stripped():
    assert run([make("imidacloprid", "1", None)]) == []
