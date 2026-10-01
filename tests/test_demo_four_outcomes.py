"""End-to-end demo test suite demonstrating the Four Foundational Outcomes:

1. Safe optimization candidate: accepted for sandbox evaluation and retained for review.
2. Evaluator / Test tampering: denied by path firewall.
3. New dependency / unsafe import: denied by AST capability firewall.
4. Statistically insignificant speedup: evaluated hermetically but not retained.
"""
import pytest
from src.cli import run_pipeline


@pytest.fixture
def contract_path():
    return "examples/sparse_matvec_contract.yaml"


@pytest.fixture
def repo_root():
    return "examples/sparse_matvec"


def test_outcome_1_safe_optimization_candidate(contract_path, repo_root):
    """Outcome 1: Valid optimization achieves >5% improvement, passes CI, and is retained for review."""
    res = run_pipeline(
        contract_path=contract_path,
        patch_path="examples/allowed_patch.diff",
        repo_root=repo_root
    )
    assert res["status"] == "RETAINED_FOR_REVIEW"
    assert res["scope_result"]["allowed"] is True
    assert res["ast_result"]["allowed"] is True
    assert res["evaluation_result"]["correctness_status"] == "PASS"
    assert res["evaluation_result"]["retained"] is True
    assert res["evaluation_result"]["improvement_percent"] >= 5.0
    assert res["evaluation_result"]["statistically_significant"] is True
    assert res["evidence_receipt"]["authority"]["release_decision"] == "HOLD"


def test_outcome_2_evaluator_tampering_denied(contract_path, repo_root):
    """Outcome 2: Attempting to modify tests/reference/ is blocked by the path firewall."""
    res = run_pipeline(
        contract_path=contract_path,
        patch_path="examples/denied_evaluator_tampering.diff",
        repo_root=repo_root
    )
    assert res["status"] == "DENIED_BY_PATH_FIREWALL"
    assert res["scope_result"]["allowed"] is False
    assert res["scope_result"]["reason_code"] == "IMMUTABLE_PATH_MODIFIED"
    assert res["evidence_receipt"]["evaluation"]["executed"] is False


def test_outcome_3_unsafe_import_denied(contract_path, repo_root):
    """Outcome 3: Attempting to import socket or os is blocked by the AST capability firewall."""
    res = run_pipeline(
        contract_path=contract_path,
        patch_path="examples/denied_unsafe_import.diff",
        repo_root=repo_root
    )
    assert res["status"] == "DENIED_BY_AST_FIREWALL"
    assert res["ast_result"]["allowed"] is False
    assert "PROHIBITED" in res["ast_result"]["reason_code"]
    assert res["evidence_receipt"]["evaluation"]["executed"] is False


def test_outcome_4_insignificant_speedup_not_retained(contract_path, repo_root):
    """Outcome 4: Trivial change passes correctness but does not meet 5% threshold or fails CI test."""
    res = run_pipeline(
        contract_path=contract_path,
        patch_path="examples/insignificant_patch.diff",
        repo_root=repo_root
    )
    assert res["status"] == "EVALUATED_NOT_RETAINED"
    assert res["scope_result"]["allowed"] is True
    assert res["ast_result"]["allowed"] is True
    assert res["evaluation_result"]["correctness_status"] == "PASS"
    assert res["evaluation_result"]["retained"] is False
    assert res["evaluation_result"]["fitness_status"] == "REJECTED_FITNESS_INSUFFICIENT"
    assert res["evidence_receipt"]["authority"]["release_decision"] == "DENY"
