"""Tests for OCCR Governance Gate."""
import json
import pytest
from src.occr_gate import (
    AuthorityLevel,
    EpistemicStatus,
    OCCRExecutionGrant,
    Role,
    audit_and_authorize_result,
    issue_execution_grant
)
from src.backend_truth import BackendClass, BackendExecutionManifest, ClaimLevel


@pytest.fixture
def policy_bundle():
    with open("policy/occr_policy_bundle.json", "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def contract():
    return {
        "contract_id": "test-contract-v1",
        "authority": {
            "candidate_status": "PROPOSAL_ONLY",
            "sandbox_execution": "REQUIRES_OCCR_GRANT",
            "source_merge": "HUMAN_APPROVAL_REQUIRED",
            "deployment": "BLOCKED",
            "customer_claim_allowed": False
        }
    }


def test_issue_execution_grant_ai_proposer(policy_bundle, contract):
    """AI proposer receives sandbox-only grant with no network."""
    grant = issue_execution_grant(
        actor_id="agent-gemini-pro-1",
        actor_role=Role.ROLE_AI_PROPOSER,
        contract=contract,
        contract_hash="sha256:abcd1234abcd1234",
        policy_bundle=policy_bundle,
        ttl_seconds=300.0
    )
    assert grant.actor_role == Role.ROLE_AI_PROPOSER
    assert not grant.allow_network
    assert not grant.allow_filesystem_write
    assert not grant.is_expired()
    assert grant.grant_digest.startswith("sha256:")


def test_unauthorized_role_cannot_request_grant(policy_bundle, contract):
    """Role without execution request privileges is denied."""
    with pytest.raises(PermissionError):
        issue_execution_grant(
            actor_id="guest-user",
            actor_role=Role.ROLE_SYSTEM_RELEASE_MANAGER,  # Release manager cannot propose candidates
            contract=contract,
            contract_hash="sha256:abcd",
            policy_bundle=policy_bundle
        )


def test_occr_audit_retained_candidate(policy_bundle, contract):
    """Retained candidate receives HUMAN_APPROVAL_REQUIRED for merge, but deployment remains BLOCKED."""
    grant = issue_execution_grant(
        actor_id="agent-gemini-pro-1",
        actor_role=Role.ROLE_AI_PROPOSER,
        contract=contract,
        contract_hash="sha256:contract123",
        policy_bundle=policy_bundle
    )
    receipt = audit_and_authorize_result(
        grant=grant,
        contract=contract,
        scope_result={"allowed": True},
        ast_result={"allowed": True},
        eval_result={"correctness_status": "PASS", "retained": True},
        evidence_receipt={
            "contract_hash": "sha256:contract123",
            "candidate_hash": "sha256:cand999",
            "lineage_merkle_root": "sha256:merkle000"
        }
    )
    assert receipt.compliant is True
    assert receipt.epistemic_status == EpistemicStatus.RETAINED_FOR_REVIEW
    assert receipt.execution_authority == AuthorityLevel.SANDBOX_EVALUATION_ONLY
    assert receipt.merge_authority == AuthorityLevel.HUMAN_APPROVAL_REQUIRED
    assert receipt.deployment_authority == AuthorityLevel.BLOCKED
    assert receipt.customer_claim_allowed is False


def test_occr_audit_failed_correctness(policy_bundle, contract):
    """Candidate that fails correctness is marked EVALUATED_NOT_RETAINED and merge is BLOCKED."""
    grant = issue_execution_grant(
        actor_id="agent-gemini-pro-1",
        actor_role=Role.ROLE_AI_PROPOSER,
        contract=contract,
        contract_hash="sha256:contract123",
        policy_bundle=policy_bundle
    )
    receipt = audit_and_authorize_result(
        grant=grant,
        contract=contract,
        scope_result={"allowed": True},
        ast_result={"allowed": True},
        eval_result={"correctness_status": "FAIL", "retained": False},
        evidence_receipt={
            "contract_hash": "sha256:contract123",
            "candidate_hash": "sha256:cand_buggy",
            "lineage_merkle_root": "sha256:merkle000"
        }
    )
    assert receipt.compliant is False
    assert receipt.epistemic_status == EpistemicStatus.EVALUATED_NOT_RETAINED
    assert receipt.merge_authority == AuthorityLevel.BLOCKED
    assert any("Correctness tests did not pass" in v for v in receipt.violations)


def test_expired_grant_rejected(policy_bundle, contract):
    """Expired grant causes compliance failure."""
    grant = issue_execution_grant(
        actor_id="agent-gemini-pro-1",
        actor_role=Role.ROLE_AI_PROPOSER,
        contract=contract,
        contract_hash="sha256:contract123",
        policy_bundle=policy_bundle,
        ttl_seconds=0.01  # Immediate expiry
    )
    import time
    time.sleep(0.02)
    assert grant.is_expired()

    receipt = audit_and_authorize_result(
        grant=grant,
        contract=contract,
        scope_result={"allowed": True},
        ast_result={"allowed": True},
        eval_result={"correctness_status": "PASS", "retained": True},
        evidence_receipt={
            "contract_hash": "sha256:contract123",
            "candidate_hash": "sha256:cand999",
            "lineage_merkle_root": "sha256:merkle000"
        }
    )
    assert not receipt.compliant
    assert any("expired" in v for v in receipt.violations)
