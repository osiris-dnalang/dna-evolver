"""Unit tests for Cryptographic Evidence Receipts and Authority Gates."""
import pytest
from src.validate_contract import load_contract
from src.emit_evidence_receipt import canonical_json_bytes, emit_evidence_receipt


@pytest.fixture
def contract():
    return load_contract("examples/sparse_matvec_contract.yaml")


def test_canonical_json_determinism():
    d1 = {"b": 2, "a": 1, "nested": {"z": 10, "y": 20}}
    d2 = {"nested": {"y": 20, "z": 10}, "a": 1, "b": 2}
    assert canonical_json_bytes(d1) == canonical_json_bytes(d2)


def test_evidence_receipt_emission(contract):
    receipt = emit_evidence_receipt(
        contract=contract,
        patch_str="--- a/dummy\n+++ b/dummy\n",
        scope_result={"allowed": True, "reason_code": "SCOPE_VALID"},
        ast_result={"allowed": True, "reason_code": "AST_VALID", "details": {"changed": 1}},
        eval_result={
            "evaluation_executed": True,
            "correctness_status": "PASS",
            "test_output_hash": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
            "benchmark_samples_hash": "sha256:2222222222222222222222222222222222222222222222222222222222222222",
            "retained": True,
            "fitness_status": "RETAINED_FOR_REVIEW"
        }
    )

    assert receipt["artifact_kind"] == "dna.evidence_record/v1"
    assert receipt["candidate_hash"].startswith("sha256:")
    assert receipt["authority"]["candidate_status"] == "PROPOSAL_ONLY"
    assert receipt["authority"]["execution_authority"] == "NONE"
    assert receipt["authority"]["source_merge"] == "HUMAN_APPROVAL_REQUIRED"
    assert receipt["authority"]["release_decision"] == "HOLD"
    assert receipt["authority"]["customer_claim_allowed"] is False
