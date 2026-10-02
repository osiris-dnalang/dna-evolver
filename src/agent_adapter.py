"""Agent Adapter for Gemini / ADK / Antigravity Agent Integration.

Enforces the core architectural sequence:
Gemini proposes -> DNA-Lang validates and constrains -> sandbox evaluates -> OCCR authorizes -> human promotes.

The model is strictly a candidate generator:
- It never touches deployment or policy-write credentials.
- It receives typed contracts, current Pareto frontier, and negative result errata.
- Its proposals are governed by ephemeral, sandbox-only execution grants.
"""
from dataclasses import dataclass, field
import hashlib
import json
import time
from typing import Any, Dict, List, Optional

from src.backend_truth import BackendClass, BackendExecutionManifest, ClaimLevel
from src.cli import run_pipeline
from src.emit_evidence_receipt import canonical_json_bytes
from src.occr_gate import (
    AuthorityLevel,
    EpistemicStatus,
    OCCRExecutionGrant,
    OCCRComplianceReceipt,
    Role,
    audit_and_authorize_result,
    issue_execution_grant
)
from src.program_database import ProgramDatabase, CandidateRecord
from src.validate_contract import load_contract, validate_contract


@dataclass
class CandidateProposal:
    """Typed proposal submitted by a Gemini / ADK / Antigravity agent."""
    contract_id: str
    parent_candidate_hash: str
    generation: int
    model_id: str
    mutation_rationale: str
    patch_diff: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "parent_candidate_hash": self.parent_candidate_hash,
            "generation": self.generation,
            "model_id": self.model_id,
            "mutation_rationale": self.mutation_rationale,
            "patch_diff": self.patch_diff,
            "metadata": self.metadata
        }


@dataclass
class AgentFeedbackReceipt:
    """Typed feedback returned to the model after governed evaluation."""
    proposal_status: str
    retained_for_review: bool
    correctness_status: str
    improvement_percent: Optional[float]
    statistically_significant: bool
    epistemic_status: str
    merge_authority: str
    deployment_authority: str
    candidate_hash: str
    lineage_merkle_root: str
    violations: List[str]
    guidance_for_next_generation: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposal_status": self.proposal_status,
            "retained_for_review": self.retained_for_review,
            "correctness_status": self.correctness_status,
            "improvement_percent": self.improvement_percent,
            "statistically_significant": self.statistically_significant,
            "epistemic_status": self.epistemic_status,
            "merge_authority": self.merge_authority,
            "deployment_authority": self.deployment_authority,
            "candidate_hash": self.candidate_hash,
            "lineage_merkle_root": self.lineage_merkle_root,
            "violations": self.violations,
            "guidance_for_next_generation": self.guidance_for_next_generation
        }


class GovernedAgentExecutor:
    """Executes agent-proposed candidate mutations under OCCR governance and DNA-Lang contracts."""

    def __init__(
        self,
        contract_path: str,
        repo_root: str,
        policy_bundle_path: str = "policy/occr_policy_bundle.json",
        program_db: Optional[ProgramDatabase] = None
    ):
        self.contract_path = contract_path
        self.repo_root = repo_root
        self.contract = load_contract(contract_path)
        valid, errors = validate_contract(self.contract)
        if not valid:
            raise ValueError(f"Contract invalid: {errors}")

        with open(policy_bundle_path, "r", encoding="utf-8") as f:
            self.policy_bundle = json.load(f)

        self.program_db = program_db or ProgramDatabase()

    def build_agent_context(self) -> Dict[str, Any]:
        """Builds bounded prompt context for Gemini/ADK agent generation."""
        pareto_cands = self.program_db.get_pareto_candidates()
        neg_results = self.program_db.get_negative_results()

        return {
            "system_invariant": (
                "You are an algorithmic mutation proposer. "
                "You have PROPOSAL_ONLY authority. You cannot merge, deploy, or alter policy. "
                "All candidates are tested hermetically against reference suites."
            ),
            "contract_id": self.contract.get("contract_id"),
            "target": self.contract.get("target"),
            "mutable_paths": self.contract.get("scope", {}).get("mutable_paths", []),
            "immutable_paths": self.contract.get("scope", {}).get("immutable_paths", []),
            "ast_constraints": self.contract.get("ast_constraints", {}),
            "budget": self.contract.get("budget", {}),
            "current_pareto_frontier": [c.to_dict() for c in pareto_cands[-3:]],
            "known_negative_results_to_avoid": [
                {
                    "failure_category": n.failure_category,
                    "failure_message": n.failure_message,
                    "patch_summary": n.patch_summary
                }
                for n in neg_results[-5:]
            ]
        }

    def evaluate_proposal(self, proposal: CandidateProposal) -> AgentFeedbackReceipt:
        """Processes an agent proposal through the 5-step governed pipeline."""
        contract_bytes = canonical_json_bytes(self.contract)
        contract_hash = f"sha256:{hashlib.sha256(contract_bytes).hexdigest()}"
        grant = issue_execution_grant(
            actor_id=proposal.model_id,
            actor_role=Role.ROLE_AI_PROPOSER,
            contract=self.contract,
            contract_hash=contract_hash,
            policy_bundle=self.policy_bundle,
            ttl_seconds=300.0
        )

        # 2. Execute hermetic pipeline under DNA-Lang contracts
        pipeline_res = run_pipeline(
            contract_path=self.contract_path,
            repo_root=self.repo_root,
            patch_str=proposal.patch_diff
        )

        scope_res = pipeline_res.get("scope_result", {})
        ast_res = pipeline_res.get("ast_result", {})
        eval_res = pipeline_res.get("evaluation_result", {})
        receipt = pipeline_res.get("evidence_receipt", {})

        # 3. Audit via OCCR Governance Gate
        backend_manifest = BackendExecutionManifest(
            backend_id="local_sandbox_qpu_sim",
            backend_class=BackendClass.SIMULATOR,
            is_mock=False
        )
        occr_receipt = audit_and_authorize_result(
            grant=grant,
            contract=self.contract,
            scope_result=scope_res,
            ast_result=ast_res,
            eval_result=eval_res,
            evidence_receipt=receipt,
            backend_manifest=backend_manifest
        )

        # 4. Record in Program Database
        cand_hash = receipt.get("candidate_hash", "unknown")
        self.program_db.record_candidate(
            candidate_hash=cand_hash,
            parent_candidate_hash=proposal.parent_candidate_hash,
            generation=proposal.generation,
            contract_id=self.contract.get("contract_id", ""),
            patch_summary=proposal.mutation_rationale,
            scope_res=scope_res,
            ast_res=ast_res,
            eval_res=eval_res,
            receipt=receipt
        )

        # 5. Formulate structured guidance for next generation
        guidance = "Proposal retained on Pareto frontier. Continue refining in this branch."
        if not occr_receipt.compliant:
            guidance = f"Candidate rejected due to: {'; '.join(occr_receipt.violations)}. Do not repeat this pattern."
        elif not eval_res.get("retained", False):
            guidance = f"Correctness passed but improvement insufficient ({eval_res.get('improvement_percent', 0.0):.2f}%). Focus on inner loop vectorization."

        return AgentFeedbackReceipt(
            proposal_status=pipeline_res.get("status", "UNKNOWN"),
            retained_for_review=eval_res.get("retained", False) and occr_receipt.compliant,
            correctness_status=eval_res.get("correctness_status", "NOT_RUN"),
            improvement_percent=eval_res.get("improvement_percent"),
            statistically_significant=eval_res.get("statistically_significant", False),
            epistemic_status=occr_receipt.epistemic_status.value,
            merge_authority=occr_receipt.merge_authority.value,
            deployment_authority=occr_receipt.deployment_authority.value,
            candidate_hash=cand_hash,
            lineage_merkle_root=occr_receipt.lineage_merkle_root,
            violations=occr_receipt.violations,
            guidance_for_next_generation=guidance
        )
