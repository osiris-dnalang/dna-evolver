"""Integration test verifying evolutionary optimization on the qLDPC Decoder Kernel target."""
import pytest
from src.cli import run_pipeline


def test_qldpc_decoder_safe_optimization_retained():
    """Verify that vectorizing the qLDPC Min-Sum decoder achieves >5% gain and is retained."""
    res = run_pipeline(
        contract_path="examples/qldpc_decoder_contract.yaml",
        patch_path="examples/qldpc_allowed_vectorized_patch.diff",
        repo_root="examples/qldpc_decoder"
    )
    assert res["status"] == "RETAINED_FOR_REVIEW"
    assert res["scope_result"]["allowed"] is True
    assert res["ast_result"]["allowed"] is True
    assert res["evaluation_result"]["correctness_status"] == "PASS"
    assert res["evaluation_result"]["retained"] is True
    assert res["evaluation_result"]["improvement_percent"] >= 5.0
    assert res["evaluation_result"]["statistically_significant"] is True
    assert res["evidence_receipt"]["authority"]["release_decision"] == "HOLD"
    assert "lineage_merkle_root" in res["evidence_receipt"]


def test_qldpc_decoder_tampering_denied():
    """Verify that tampering with frozen syndromes is denied by path firewall."""
    tamper_patch = (
        "--- benchmarks/frozen_inputs/qldpc_syndromes_n72.json\n"
        "+++ benchmarks/frozen_inputs/qldpc_syndromes_n72.json\n"
        "@@ -1,3 +1,3 @@\n"
        "-{\n"
        "+{\"tampered\": true,\n"
    )
    res = run_pipeline(
        contract_path="examples/qldpc_decoder_contract.yaml",
        patch_str=tamper_patch,
        repo_root="examples/qldpc_decoder"
    )
    assert res["status"] == "DENIED_BY_PATH_FIREWALL"
    assert res["scope_result"]["reason_code"] == "IMMUTABLE_PATH_MODIFIED"
