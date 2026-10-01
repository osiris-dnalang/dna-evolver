"""Unit tests for Hermetic Evaluator and Integrity Gates."""
import copy
import pytest
from src.validate_contract import load_contract
from src.run_hermetic_evaluator import (
    compute_paired_bootstrap_ci,
    run_hermetic_evaluation
)


@pytest.fixture
def contract():
    return load_contract("examples/sparse_matvec_contract.yaml")


@pytest.fixture
def repo_root():
    return "examples/sparse_matvec"


def test_evaluator_integrity_check_failure(contract, repo_root):
    c = copy.deepcopy(contract)
    # Intentionally corrupt expected hash
    c["evaluator"]["reference_tests_tree_sha256"] = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    res = run_hermetic_evaluation(repo_root, None, c)
    assert res["evaluation_executed"] is False
    assert res["reason_code"] == "EVALUATOR_INTEGRITY_COMPROMISED"


def test_correctness_failure_halts_evaluation(contract, repo_root):
    # Patch that breaks mathematical correctness
    buggy_patch = (
        "--- src/kernel/sparse_matvec.py\n"
        "+++ src/kernel/sparse_matvec.py\n"
        "@@ -10,3 +10,4 @@\n"
        "     y = [0.0] * num_rows\n"
        "+    return [999.0] * num_rows\n"
    )
    res = run_hermetic_evaluation(repo_root, buggy_patch, contract)
    assert res["evaluation_executed"] is True
    assert res["correctness_status"] == "FAIL"
    assert res["reason_code"] == "CORRECTNESS_FAILED"
    assert res["retained"] is False
    # Ensure performance benchmark was NOT executed
    assert "baseline_median_ms" not in res


def test_paired_bootstrap_ci_detection():
    # Candidate 2x faster than baseline
    base = [2.0, 2.1, 1.9, 2.05, 2.0]
    cand = [1.0, 1.05, 0.95, 1.02, 1.0]
    ci_low, ci_high = compute_paired_bootstrap_ci(base, cand, n_resamples=500, confidence_level=0.99)
    assert ci_high < 1.0
    assert 0.4 < ci_low < 0.6
