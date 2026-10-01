"""Evidence Record and Cryptographic Receipt Emitter for DNA-Lang Evolver."""
import hashlib
import json
import os
import platform
import sys
from typing import Any, Dict, Optional


def canonical_json_bytes(obj: Any) -> bytes:
    """Serialize object to deterministic canonical JSON bytes (OSIRIS-CANONICAL-JSON-V1)."""
    return json.dumps(
        obj,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":")
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    """Compute SHA-256 hex string."""
    return hashlib.sha256(data).hexdigest()


def get_environment_manifest() -> Dict[str, Any]:
    """Capture environment digest for reproducibility tracking."""
    return {
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
    }


def emit_evidence_receipt(
    contract: Dict[str, Any],
    patch_str: Optional[str],
    scope_result: Dict[str, Any],
    ast_result: Dict[str, Any],
    eval_result: Dict[str, Any],
    parent_candidate_hash: str = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
) -> Dict[str, Any]:
    """Generate a tamper-evident cryptographic receipt for an evaluated candidate."""
    contract_bytes = canonical_json_bytes(contract)
    contract_hash = f"sha256:{sha256_hex(contract_bytes)}"

    patch_bytes = (patch_str or "").encode("utf-8")
    patch_hash = f"sha256:{sha256_hex(patch_bytes)}"

    ast_diff_bytes = canonical_json_bytes(ast_result.get("details", {}))
    ast_diff_hash = f"sha256:{sha256_hex(ast_diff_bytes)}"

    env_manifest = get_environment_manifest()
    env_manifest_hash = f"sha256:{sha256_hex(canonical_json_bytes(env_manifest))}"

    base_commit = contract.get("seed", {}).get("commit", "unknown")
    test_out_hash = eval_result.get("test_output_hash", "sha256:0000000000000000000000000000000000000000000000000000000000000000")
    bench_samples_hash = eval_result.get("benchmark_samples_hash", "sha256:0000000000000000000000000000000000000000000000000000000000000000")

    # Compute Merkle root of the execution evidence tree
    merkle_components = [
        f"base:{base_commit}",
        f"patch:{patch_hash}",
        f"contract:{contract_hash}",
        f"ast:{ast_diff_hash}",
        f"test:{test_out_hash}",
        f"bench:{bench_samples_hash}",
        f"env:{env_manifest_hash}"
    ]
    merkle_root_hash = f"sha256:{sha256_hex('|'.join(merkle_components).encode('utf-8'))}"

    is_retained = eval_result.get("retained", False)

    receipt = {
        "artifact_kind": "dna.evidence_record/v1",
        "candidate_hash": merkle_root_hash,
        "parent_candidate_hash": parent_candidate_hash,
        "contract_id": contract.get("contract_id"),
        "contract_hash": contract_hash,
        "source_commit": base_commit,
        "patch_hash": patch_hash,
        "ast_diff_hash": ast_diff_hash,
        "environment_manifest_hash": env_manifest_hash,
        "evaluator_image_digest": contract.get("evaluator", {}).get("image_digest"),
        "static_validation": {
            "scope_allowed": scope_result.get("allowed", False),
            "scope_reason": scope_result.get("reason_code"),
            "ast_allowed": ast_result.get("allowed", False),
            "ast_reason": ast_result.get("reason_code")
        },
        "evaluation": {
            "executed": eval_result.get("evaluation_executed", False),
            "correctness_status": eval_result.get("correctness_status", "NOT_RUN"),
            "test_output_hash": test_out_hash,
            "benchmark_samples_hash": bench_samples_hash,
            "baseline_median_ms": eval_result.get("baseline_median_ms"),
            "candidate_median_ms": eval_result.get("candidate_median_ms"),
            "improvement_percent": eval_result.get("improvement_percent"),
            "paired_bootstrap_ci_99": eval_result.get("paired_bootstrap_ci_99"),
            "statistically_significant": eval_result.get("statistically_significant", False),
            "fitness_status": eval_result.get("fitness_status", "REJECTED")
        },
        "authority": {
            "candidate_status": "PROPOSAL_ONLY",
            "execution_authority": "NONE",
            "source_merge": "HUMAN_APPROVAL_REQUIRED",
            "release_decision": "HOLD" if is_retained else "DENY",
            "customer_claim_allowed": False
        },
        "lineage_merkle_root": merkle_root_hash
    }

    return receipt
