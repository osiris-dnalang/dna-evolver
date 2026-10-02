"""Tests for active IBM Quantum backend discovery and fail-closed selection."""
import pytest
from src.backend_discovery import (
    ActiveIBMBackendResolver,
    BackendAuthenticationError,
    BackendEligibilityPolicy,
    CandidateBackendMetadata,
    NoEligibleBackendError
)


@pytest.fixture
def sample_backends():
    return [
        {
            "name": "ibm_sherbrooke",
            "status": "active",
            "operational": True,
            "processor_family": "Eagle",
            "num_qubits": 127,
            "coupling_map": [[0, 1], [1, 2], [2, 3]],
            "native_basis_gates": ["cz", "rz", "sx", "x", "id"],
            "calibration_timestamp_utc": "2026-10-02T00:00:00Z",
            "median_2q_error": 0.0085,
            "median_t1_us": 210.0,
            "median_t2_us": 145.0,
            "pending_jobs": 42,
            "is_simulator": False
        },
        {
            "name": "ibm_brisbane",
            "status": "maintenance",  # Non-operational
            "operational": False,
            "processor_family": "Eagle",
            "num_qubits": 127,
            "coupling_map": [[0, 1], [1, 2]],
            "native_basis_gates": ["cz", "rz", "sx", "x"],
            "calibration_timestamp_utc": "2026-10-01T22:00:00Z",
            "median_2q_error": 0.0079,
            "median_t1_us": 230.0,
            "median_t2_us": 160.0,
            "pending_jobs": 0,
            "is_simulator": False
        },
        {
            "name": "ibm_kyiv",
            "status": "active",
            "operational": True,
            "processor_family": "Eagle",
            "num_qubits": 127,
            "coupling_map": [[0, 1], [1, 2], [2, 3]],
            "native_basis_gates": ["cz", "rz", "sx", "x"],
            "calibration_timestamp_utc": "2026-10-02T01:30:00Z",
            "median_2q_error": 0.0092,
            "median_t1_us": 195.0,
            "median_t2_us": 130.0,
            "pending_jobs": 15,
            "is_simulator": False
        },
        {
            "name": "simulator_mps",
            "status": "active",
            "operational": True,
            "processor_family": "Simulator",
            "num_qubits": 100,
            "coupling_map": [],
            "native_basis_gates": ["cz", "rz", "sx", "x"],
            "calibration_timestamp_utc": "2026-10-02T00:00:00Z",
            "median_2q_error": 0.0,
            "median_t1_us": 9999.0,
            "median_t2_us": 9999.0,
            "pending_jobs": 0,
            "is_simulator": True
        }
    ]


def test_dynamic_discovery_qualifies_best_backend(sample_backends):
    """Active resolver discovers inventory, evaluates policy, and picks lowest 2Q error."""
    policy = BackendEligibilityPolicy(
        min_qubits=16,
        required_basis_gates=("cz", "rz", "sx", "x"),
        allow_simulator=False,
        ranking_metric="median_2q_error",
        ranking_order="asc"
    )
    resolver = ActiveIBMBackendResolver(policy=policy, provider_service=sample_backends)
    manifest = resolver.resolve()

    manifest_dict = manifest.to_dict()["backend_resolution"]
    assert manifest_dict["selected_backend"] == "ibm_sherbrooke"
    assert len(manifest_dict["candidate_backends"]) == 4

    # Verify candidate evaluations
    cand_map = {c["backend_name"]: c for c in manifest_dict["candidate_backends"]}
    assert cand_map["ibm_sherbrooke"]["eligible"] is True
    assert cand_map["ibm_kyiv"]["eligible"] is True
    assert cand_map["ibm_brisbane"]["eligible"] is False
    assert "not operational" in cand_map["ibm_brisbane"]["reason"]
    assert cand_map["simulator_mps"]["eligible"] is False
    assert "Simulator fallback prohibited" in cand_map["simulator_mps"]["reason"]


def test_fail_closed_when_no_backend_satisfies_qubit_policy(sample_backends):
    """When preregistered qubit requirement cannot be satisfied, fail closed."""
    strict_policy = BackendEligibilityPolicy(min_qubits=400)
    resolver = ActiveIBMBackendResolver(policy=strict_policy, provider_service=sample_backends)

    with pytest.raises(NoEligibleBackendError) as exc_info:
        resolver.resolve()

    assert "Fail-closed: No eligible backend discovered" in str(exc_info.value)


def test_fail_closed_when_all_devices_in_maintenance():
    """All backends down or maintenance triggers fail-closed with 0 eligible candidates."""
    down_backends = [
        {
            "name": "ibm_device_a",
            "status": "maintenance",
            "operational": False,
            "num_qubits": 127,
            "native_basis_gates": ["cz", "rz", "sx", "x"]
        }
    ]
    resolver = ActiveIBMBackendResolver(provider_service=down_backends)
    with pytest.raises(NoEligibleBackendError):
        resolver.resolve()


def test_missing_native_basis_gates_rejected(sample_backends):
    """Backend lacking required native gates is rejected."""
    policy = BackendEligibilityPolicy(required_basis_gates=("cz", "rz", "sx", "x", "ecr"))
    resolver = ActiveIBMBackendResolver(policy=policy, provider_service=sample_backends)
    with pytest.raises(NoEligibleBackendError) as exc_info:
        resolver.resolve()
    assert "Missing required native basis gates" in str(exc_info.value)


def test_fail_closed_on_provider_auth_failure():
    """Provider connection or authentication errors raise BackendAuthenticationError."""
    resolver = ActiveIBMBackendResolver(provider_service=object())  # Invalid service
    with pytest.raises(BackendAuthenticationError):
        resolver.query_inventory()


def test_deterministic_ranking_by_queue_depth(sample_backends):
    """Preregistered ranking policy selects lowest pending jobs when configured."""
    queue_policy = BackendEligibilityPolicy(
        ranking_metric="pending_jobs",
        ranking_order="asc"
    )
    resolver = ActiveIBMBackendResolver(policy=queue_policy, provider_service=sample_backends)
    manifest = resolver.resolve()
    # ibm_kyiv has 15 pending jobs vs ibm_sherbrooke's 42
    assert manifest.selected_backend == "ibm_kyiv"


def test_manifest_contains_topology_and_calibration_hashes(sample_backends):
    """Selected manifest produces RFC 8785 compliant hashes for topology and calibration."""
    resolver = ActiveIBMBackendResolver(provider_service=sample_backends)
    manifest = resolver.resolve()
    d = manifest.to_dict()["backend_resolution"]

    for cand in d["candidate_backends"]:
        assert cand["topology_hash"].startswith("sha256:")
        assert cand["target_hash"].startswith("sha256:")
        assert cand["calibration_snapshot_hash"].startswith("sha256:")

    assert manifest.manifest_sha256() is not None
    assert len(manifest.manifest_sha256()) == 64
