"""Tests for Agent Adapter integrating Gemini / ADK with DNA-Lang governance."""
import pytest
from src.agent_adapter import (
    AgentFeedbackReceipt,
    CandidateProposal,
    GovernedAgentExecutor
)
from src.program_database import ProgramDatabase


@pytest.fixture
def qldpc_executor():
    return GovernedAgentExecutor(
        contract_path="examples/qldpc_decoder_contract.yaml",
        repo_root="examples/qldpc_decoder",
        policy_bundle_path="policy/occr_policy_bundle.json"
    )


def test_agent_context_builder(qldpc_executor):
    """Context builder includes system invariants, targets, and negative results."""
    ctx = qldpc_executor.build_agent_context()
    assert "PROPOSAL_ONLY" in ctx["system_invariant"]
    assert ctx["contract_id"] == "qldpc_minsum_latency_v1"
    assert "src/kernel/**" in ctx["mutable_paths"]
    assert "evaluator/**" in ctx["immutable_paths"]
    assert "known_negative_results_to_avoid" in ctx


def test_agent_proposal_retained(qldpc_executor):
    """Valid agent optimization proposal is evaluated, authorized, and retained for review."""
    with open("examples/qldpc_allowed_vectorized_patch.diff", "r", encoding="utf-8") as f:
        diff_content = f.read()

    proposal = CandidateProposal(
        contract_id="qldpc_minsum_latency_v1",
        parent_candidate_hash="sha256:0000000000000000000000000000000000000000000000000000000000000000",
        generation=1,
        model_id="gemini-2.5-pro",
        mutation_rationale="Vectorize syndrome check and sign parity in Min-Sum kernel",
        patch_diff=diff_content
    )

    feedback = qldpc_executor.evaluate_proposal(proposal)
    assert feedback.proposal_status == "RETAINED_FOR_REVIEW"
    assert feedback.retained_for_review is True
    assert feedback.correctness_status == "PASS"
    assert feedback.improvement_percent >= 5.0
    assert feedback.statistically_significant is True
    assert feedback.merge_authority == "HUMAN_APPROVAL_REQUIRED"
    assert feedback.deployment_authority == "BLOCKED"
    assert feedback.epistemic_status == "RETAINED_FOR_REVIEW"
    assert len(qldpc_executor.program_db.get_pareto_candidates()) == 1


def test_agent_proposal_rejected_on_firewall_violation(qldpc_executor):
    """Agent proposal attempting to tamper with immutable benchmarks is denied and logged as negative result."""
    tamper_diff = (
        "--- benchmarks/frozen_inputs/qldpc_syndromes_n72.json\n"
        "+++ benchmarks/frozen_inputs/qldpc_syndromes_n72.json\n"
        "@@ -1,3 +1,3 @@\n"
        "-{\n"
        "+{\"tampered\": true,\n"
    )

    proposal = CandidateProposal(
        contract_id="qldpc-minsum-optimization-v1",
        parent_candidate_hash="sha256:0000",
        generation=2,
        model_id="gemini-2.5-flash",
        mutation_rationale="Attempted mock reduction",
        patch_diff=tamper_diff
    )

    feedback = qldpc_executor.evaluate_proposal(proposal)
    assert feedback.proposal_status == "DENIED_BY_PATH_FIREWALL"
    assert feedback.retained_for_review is False
    assert feedback.merge_authority == "BLOCKED"
    assert feedback.deployment_authority == "BLOCKED"
    assert len(qldpc_executor.program_db.get_negative_results()) == 1
    assert "IMMUTABLE_PATH_MODIFIED" in qldpc_executor.program_db.get_negative_results()[0].failure_message
