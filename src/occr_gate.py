"""OCCR Governance Gate.

Enforces capability boundaries, role-based execution authority,
epistemic status tracking, and backend truthfulness.

Invariants:
1. 'OCCR should not decide whether an idea is true. It should decide what the system is allowed to treat that idea as.'
2. 'Candidate quality != execution authority != merge authority != deployment authority.'
3. An AI agent proposer can only receive an ephemeral SANDBOX_EVALUATION_ONLY grant.
4. Source merge requires human approval; deployment is blocked for unpromoted candidates.
"""
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional

from src.backend_truth import (
    BackendClass,
    BackendExecutionManifest,
    ClaimLevel,
    audit_backend_truthfulness
)
from src.emit_evidence_receipt import canonical_json_bytes


class Role(str, Enum):
    ROLE_AI_PROPOSER = "ROLE_AI_PROPOSER"
    ROLE_HUMAN_REVIEWER = "ROLE_HUMAN_REVIEWER"
    ROLE_SYSTEM_RELEASE_MANAGER = "ROLE_SYSTEM_RELEASE_MANAGER"


class EpistemicStatus(str, Enum):
    PROPOSED = "PROPOSED"
    EVALUATED_NOT_RETAINED = "EVALUATED_NOT_RETAINED"
    RETAINED_FOR_REVIEW = "RETAINED_FOR_REVIEW"
    MERGE_APPROVED = "MERGE_APPROVED"
    DEPLOYED_VERIFIED = "DEPLOYED_VERIFIED"


class AuthorityLevel(str, Enum):
    PROPOSAL_ONLY = "PROPOSAL_ONLY"
    SANDBOX_EVALUATION_ONLY = "SANDBOX_EVALUATION_ONLY"
    HUMAN_APPROVAL_REQUIRED = "HUMAN_APPROVAL_REQUIRED"
    BLOCKED = "BLOCKED"
    AUTHORIZED = "AUTHORIZED"


@dataclass
class OCCRExecutionGrant:
    grant_id: str
    actor_id: str
    actor_role: Role
    contract_id: str
    contract_hash: str
    issued_at: float
    ttl_seconds: float
    allowed_actions: List[str]
    denied_actions: List[str]
    allow_network: bool = False
    allow_filesystem_write: bool = False
    grant_digest: str = ""

    def is_expired(self, current_time: Optional[float] = None) -> bool:
        now = current_time if current_time is not None else time.time()
        return (now - self.issued_at) > self.ttl_seconds

    def to_dict(self) -> Dict[str, Any]:
        return {
            "grant_id": self.grant_id,
            "actor_id": self.actor_id,
            "actor_role": self.actor_role.value,
            "contract_id": self.contract_id,
            "contract_hash": self.contract_hash,
            "issued_at": self.issued_at,
            "ttl_seconds": self.ttl_seconds,
            "allowed_actions": self.allowed_actions,
            "denied_actions": self.denied_actions,
            "allow_network": self.allow_network,
            "allow_filesystem_write": self.allow_filesystem_write,
            "grant_digest": self.grant_digest
        }


@dataclass
class OCCRComplianceReceipt:
    receipt_id: str
    grant_id: str
    candidate_hash: str
    contract_hash: str
    epistemic_status: EpistemicStatus
    execution_authority: AuthorityLevel
    merge_authority: AuthorityLevel
    deployment_authority: AuthorityLevel
    customer_claim_allowed: bool
    claim_ceiling: ClaimLevel
    backend_manifest_digest: Optional[str]
    lineage_merkle_root: str
    timestamp: float
    compliant: bool
    violations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "grant_id": self.grant_id,
            "candidate_hash": self.candidate_hash,
            "contract_hash": self.contract_hash,
            "epistemic_status": self.epistemic_status.value,
            "authority": {
                "execution_authority": self.execution_authority.value,
                "merge_authority": self.merge_authority.value,
                "deployment_authority": self.deployment_authority.value,
                "customer_claim_allowed": self.customer_claim_allowed
            },
            "claims": {
                "claim_ceiling": self.claim_ceiling.value,
                "backend_manifest_digest": self.backend_manifest_digest
            },
            "lineage_merkle_root": self.lineage_merkle_root,
            "timestamp": self.timestamp,
            "compliant": self.compliant,
            "violations": self.violations
        }


def compute_grant_digest(grant_dict: Dict[str, Any]) -> str:
    """Compute deterministic sha256 digest of grant contents without grant_digest field."""
    d = {k: v for k, v in grant_dict.items() if k != "grant_digest"}
    canon_bytes = canonical_json_bytes(d)
    return f"sha256:{hashlib.sha256(canon_bytes).hexdigest()}"


def issue_execution_grant(
    actor_id: str,
    actor_role: Role,
    contract: Dict[str, Any],
    contract_hash: str,
    policy_bundle: Dict[str, Any],
    ttl_seconds: float = 300.0
) -> OCCRExecutionGrant:
    """Issues a short-lived, sandbox-only execution grant.
    
    Verifies that the actor's role permits candidate evaluation and enforces
    strict sandbox constraints (no network, bounded resources).
    """
    role_rules = policy_bundle.get("roles", {}).get(actor_role.value, {})
    allowed_actions = role_rules.get("allowed_actions", [])
    denied_actions = role_rules.get("denied_actions", [])

    if "REQUEST_SANDBOX_EVALUATION" not in allowed_actions and "PROPOSE_CANDIDATE" not in allowed_actions:
        raise PermissionError(f"Role {actor_role.value} is not authorized to request sandbox evaluation.")

    grant_id = f"grant-{hashlib.sha256(f'{actor_id}:{contract_hash}:{time.time()}'.encode('utf-8')).hexdigest()[:16]}"
    now = time.time()

    grant = OCCRExecutionGrant(
        grant_id=grant_id,
        actor_id=actor_id,
        actor_role=actor_role,
        contract_id=contract.get("contract_id", "unknown-contract"),
        contract_hash=contract_hash,
        issued_at=now,
        ttl_seconds=ttl_seconds,
        allowed_actions=["SANDBOX_EVALUATION"],
        denied_actions=denied_actions + ["NETWORK_ACCESS", "PRODUCTION_WRITE", "GIT_MERGE"],
        allow_network=False,
        allow_filesystem_write=False
    )
    grant.grant_digest = compute_grant_digest(grant.to_dict())
    return grant


def audit_and_authorize_result(
    grant: OCCRExecutionGrant,
    contract: Dict[str, Any],
    scope_result: Dict[str, Any],
    ast_result: Dict[str, Any],
    eval_result: Dict[str, Any],
    evidence_receipt: Dict[str, Any],
    backend_manifest: Optional[BackendExecutionManifest] = None
) -> OCCRComplianceReceipt:
    """Audits evaluation outputs, enforces authority boundaries, and issues an OCCR compliance receipt."""
    violations: List[str] = []

    # 1. Grant validation
    if grant.is_expired():
        violations.append("OCCR execution grant has expired.")
    if grant.contract_hash != evidence_receipt.get("contract_hash"):
        violations.append("Contract hash in evidence receipt does not match execution grant.")

    # 2. Scope & AST firewall check
    if not scope_result.get("allowed", False):
        violations.append(f"Scope firewall violation: {scope_result.get('reason_code')}")
    if not ast_result.get("allowed", False):
        violations.append(f"AST firewall violation: {ast_result.get('reason_code')}")

    # 3. Correctness check
    correctness_status = eval_result.get("correctness_status")
    if correctness_status != "PASS":
        violations.append(f"Correctness tests did not pass (status: {correctness_status}).")

    # 4. Backend truthfulness check
    claim_ceiling = ClaimLevel.THEORETICAL
    manifest_digest = None
    if backend_manifest:
        truth_audit = audit_backend_truthfulness(backend_manifest, ClaimLevel.SIMULATION_VERIFIED)
        if not truth_audit.valid:
            for v in truth_audit.violations:
                violations.append(f"Backend truth violation ({v['code']}): {v['message']}")
        claim_ceiling = truth_audit.effective_claim_ceiling
        manifest_digest = truth_audit.manifest_digest
    else:
        # Default local runner is simulator/local compute
        claim_ceiling = ClaimLevel.SIMULATION_VERIFIED

    # 5. Authority and Epistemic Status Determination
    # Invariant: Candidate quality != execution authority != merge authority != deployment authority
    retained = eval_result.get("retained", False) and len(violations) == 0

    if retained:
        epistemic_status = EpistemicStatus.RETAINED_FOR_REVIEW
        merge_authority = AuthorityLevel.HUMAN_APPROVAL_REQUIRED
    else:
        epistemic_status = EpistemicStatus.EVALUATED_NOT_RETAINED
        merge_authority = AuthorityLevel.BLOCKED

    # AI agents NEVER get automatic merge or deployment authority
    execution_authority = AuthorityLevel.SANDBOX_EVALUATION_ONLY
    deployment_authority = AuthorityLevel.BLOCKED
    customer_claim_allowed = False

    cand_h = evidence_receipt.get("candidate_hash", "unknown")
    receipt_seed = f"{grant.grant_id}:{cand_h}".encode("utf-8")
    receipt_id = f"occr-{hashlib.sha256(receipt_seed).hexdigest()[:16]}"

    return OCCRComplianceReceipt(
        receipt_id=receipt_id,
        grant_id=grant.grant_id,
        candidate_hash=evidence_receipt.get("candidate_hash", "unknown"),
        contract_hash=evidence_receipt.get("contract_hash", "unknown"),
        epistemic_status=epistemic_status,
        execution_authority=execution_authority,
        merge_authority=merge_authority,
        deployment_authority=deployment_authority,
        customer_claim_allowed=customer_claim_allowed,
        claim_ceiling=claim_ceiling,
        backend_manifest_digest=manifest_digest,
        lineage_merkle_root=evidence_receipt.get("lineage_merkle_root", ""),
        timestamp=time.time(),
        compliant=(len(violations) == 0),
        violations=violations
    )
