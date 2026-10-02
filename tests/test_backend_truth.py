"""Tests for Sprint Q0 Backend Truthfulness Guard."""
import pytest
from src.backend_truth import (
    BackendClass,
    BackendExecutionManifest,
    ClaimLevel,
    TruthViolationCode,
    audit_backend_truthfulness
)


def test_explicit_backend_id_required():
    """Empty backend id is rejected."""
    m = BackendExecutionManifest(
        backend_id="",
        backend_class=BackendClass.SIMULATOR,
        is_mock=False
    )
    res = audit_backend_truthfulness(m, ClaimLevel.SIMULATION_VERIFIED)
    assert not res.valid
    assert any(v["code"] == TruthViolationCode.UNSPECIFIED_BACKEND.value for v in res.violations)


def test_unannounced_simulator_fallback_rejected():
    """Failing back from hardware to simulator without announcing it is blocked."""
    m = BackendExecutionManifest(
        backend_id="aer_simulator",
        backend_class=BackendClass.SIMULATOR,
        is_mock=False,
        requested_backend_id="ibm_brisbane",
        fallback_occurred=False,  # Unannounced!
        fallback_reason=None
    )
    res = audit_backend_truthfulness(m, ClaimLevel.SIMULATION_VERIFIED)
    assert not res.valid
    assert any(v["code"] == TruthViolationCode.UNANNOUNCED_SIMULATOR_FALLBACK.value for v in res.violations)


def test_announced_simulator_fallback_accepted():
    """Announced fallback to simulator is accepted at simulation claim ceiling."""
    m = BackendExecutionManifest(
        backend_id="aer_simulator",
        backend_class=BackendClass.SIMULATOR,
        is_mock=False,
        requested_backend_id="ibm_brisbane",
        fallback_occurred=True,
        fallback_reason="Device queue exceeded 4 hour threshold"
    )
    res = audit_backend_truthfulness(m, ClaimLevel.SIMULATION_VERIFIED)
    assert res.valid
    assert res.effective_claim_ceiling == ClaimLevel.SIMULATION_VERIFIED


def test_mock_disguised_rejected():
    """Mock backend without is_mock=True is rejected."""
    m = BackendExecutionManifest(
        backend_id="mock_ibm_heron",
        backend_class=BackendClass.MOCK,
        is_mock=False  # Misleading!
    )
    res = audit_backend_truthfulness(m, ClaimLevel.THEORETICAL)
    assert not res.valid
    assert any(v["code"] == TruthViolationCode.MOCK_DISGUISED_AS_SIMULATOR.value for v in res.violations)


def test_simulation_promotion_to_hardware_forbidden():
    """Simulation run cannot support HARDWARE_OBSERVED claim level."""
    m = BackendExecutionManifest(
        backend_id="qiskit_aer",
        backend_class=BackendClass.SIMULATOR,
        is_mock=False
    )
    res = audit_backend_truthfulness(m, ClaimLevel.HARDWARE_OBSERVED)
    assert not res.valid
    assert any(v["code"] == TruthViolationCode.SIMULATION_PROMOTION_FORBIDDEN.value for v in res.violations)


def test_physical_hardware_requires_receipt():
    """Hardware claim without provider receipt digest is rejected."""
    m = BackendExecutionManifest(
        backend_id="ibm_brisbane",
        backend_class=BackendClass.PHYSICAL_HARDWARE,
        is_mock=False,
        execution_receipt_digest=None
    )
    res = audit_backend_truthfulness(m, ClaimLevel.HARDWARE_OBSERVED)
    assert not res.valid
    assert any(v["code"] == TruthViolationCode.MISSING_EXECUTION_RECEIPT.value for v in res.violations)


def test_physical_hardware_with_receipt_valid():
    """Physical hardware with valid provider receipt is approved."""
    m = BackendExecutionManifest(
        backend_id="ibm_brisbane",
        backend_class=BackendClass.PHYSICAL_HARDWARE,
        is_mock=False,
        execution_receipt_digest="sha256:4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a"
    )
    res = audit_backend_truthfulness(m, ClaimLevel.HARDWARE_OBSERVED)
    assert res.valid
    assert res.effective_claim_ceiling == ClaimLevel.HARDWARE_OBSERVED
    assert res.manifest_digest.startswith("sha256:")
