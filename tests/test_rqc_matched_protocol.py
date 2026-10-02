"""Tests for 3-arm resource-matched RQC protocol and statistical gates."""
import pytest
from src.rqc_matched_protocol import (
    ArmEvaluationResult,
    CircuitResourceEnvelope,
    ResourceDisparityError,
    ThreeArmMatchedTrial,
    ThreeArmRQCProtocolHarness
)


def _make_envelope(
    seed: int = 42,
    num_qubits: int = 16,
    compiled_depth: int = 20,
    two_qubit_gate_count: int = 40,
    two_qubit_gate_name: str = "cz",
    single_qubit_gate_count: int = 60,
    shot_count: int = 10000,
    qubit_indices=(0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15),
    transpiler_optimization_level: int = 1,
    transpiler_version: str = "qiskit-2.3.1",
    error_mitigation_policy: str = "none"
) -> CircuitResourceEnvelope:
    return CircuitResourceEnvelope(
        seed=seed,
        num_qubits=num_qubits,
        qubit_indices=qubit_indices,
        compiled_depth=compiled_depth,
        two_qubit_gate_count=two_qubit_gate_count,
        two_qubit_gate_name=two_qubit_gate_name,
        single_qubit_gate_count=single_qubit_gate_count,
        transpiler_optimization_level=transpiler_optimization_level,
        transpiler_version=transpiler_version,
        shot_count=shot_count,
        error_mitigation_policy=error_mitigation_policy
    )


def test_resource_matching_depth_disparity_raises():
    """Circuit depth drift (+1 depth) between arms violates the matched invariant."""
    env_rqc = _make_envelope(compiled_depth=21)  # Depth drift!
    env_control = _make_envelope(compiled_depth=20)

    trial = ThreeArmMatchedTrial(
        seed=42,
        arm_rqc=ArmEvaluationResult("ARM_A_RQC", 42, env_rqc, 0.05),
        arm_placebo=ArmEvaluationResult("ARM_B_PLACEBO", 42, env_control, 0.03),
        arm_static=ArmEvaluationResult("ARM_C_STATIC", 42, env_control, 0.02)
    )

    with pytest.raises(ResourceDisparityError) as exc_info:
        trial.validate_resource_matching()

    assert "Compiled depth disparity" in str(exc_info.value)
    assert "Depth drift is forbidden" in str(exc_info.value)


def test_resource_matching_two_qubit_gate_disparity_raises():
    """Mismatched two-qubit gate counts between arms raises ResourceDisparityError."""
    env_rqc = _make_envelope(two_qubit_gate_count=42)
    env_control = _make_envelope(two_qubit_gate_count=40)

    trial = ThreeArmMatchedTrial(
        seed=42,
        arm_rqc=ArmEvaluationResult("ARM_A_RQC", 42, env_rqc, 0.05),
        arm_placebo=ArmEvaluationResult("ARM_B_PLACEBO", 42, env_control, 0.03),
        arm_static=ArmEvaluationResult("ARM_C_STATIC", 42, env_control, 0.02)
    )

    with pytest.raises(ResourceDisparityError) as exc_info:
        trial.validate_resource_matching()

    assert "Two-qubit gate count disparity" in str(exc_info.value)


def test_resource_matching_shot_count_disparity_raises():
    """Unequal shot allocations between arms raises ResourceDisparityError."""
    env_rqc = _make_envelope(shot_count=20000)
    env_control = _make_envelope(shot_count=10000)

    trial = ThreeArmMatchedTrial(
        seed=42,
        arm_rqc=ArmEvaluationResult("ARM_A_RQC", 42, env_rqc, 0.05),
        arm_placebo=ArmEvaluationResult("ARM_B_PLACEBO", 42, env_control, 0.03),
        arm_static=ArmEvaluationResult("ARM_C_STATIC", 42, env_control, 0.02)
    )

    with pytest.raises(ResourceDisparityError) as exc_info:
        trial.validate_resource_matching()

    assert "Shot count disparity" in str(exc_info.value)


def test_resource_matching_qubit_index_disparity_raises():
    """Different physical qubit allocations raise ResourceDisparityError."""
    env_rqc = _make_envelope(qubit_indices=(0, 1, 2, 3))
    env_control = _make_envelope(qubit_indices=(4, 5, 6, 7))

    trial = ThreeArmMatchedTrial(
        seed=42,
        arm_rqc=ArmEvaluationResult("ARM_A_RQC", 42, env_rqc, 0.05),
        arm_placebo=ArmEvaluationResult("ARM_B_PLACEBO", 42, env_control, 0.03),
        arm_static=ArmEvaluationResult("ARM_C_STATIC", 42, env_control, 0.02)
    )

    with pytest.raises(ResourceDisparityError) as exc_info:
        trial.validate_resource_matching()

    assert "Qubit allocation disparity" in str(exc_info.value)


def test_causality_verified_when_rqc_beats_placebo_and_static():
    """When RQC reliably outperforms placebo and static RCS, both gates pass."""
    trials = []
    env = _make_envelope()

    for s in range(50):
        # RQC fidelity higher than Placebo and Static
        trial = ThreeArmMatchedTrial(
            seed=s,
            arm_rqc=ArmEvaluationResult("ARM_A_RQC", s, env, 0.080 + 0.005 * (s % 3)),
            arm_placebo=ArmEvaluationResult("ARM_B_PLACEBO", s, env, 0.040 + 0.003 * (s % 3)),
            arm_static=ArmEvaluationResult("ARM_C_STATIC", s, env, 0.030 + 0.002 * (s % 3))
        )
        trials.append(trial)

    harness = ThreeArmRQCProtocolHarness(n_bootstrap=500, random_seed=42)
    report = harness.evaluate_trials(trials)

    assert report.causality_verified is True
    assert report.adaptive_advantage_verified is True
    assert report.delta_informative_ci_99[0] > 0.0
    assert report.delta_adaptive_ci_99[0] > 0.0
    assert "PASSED: Feedback causality and adaptive advantage" in report.summary


def test_causality_refuted_when_placebo_matches_rqc():
    """When RQC fails to outperform placebo feedback, causality is refuted."""
    trials = []
    env = _make_envelope()

    for s in range(50):
        # RQC and Placebo share identical statistical distributions (noise)
        trial = ThreeArmMatchedTrial(
            seed=s,
            arm_rqc=ArmEvaluationResult("ARM_A_RQC", s, env, 0.050 + 0.002 * (s % 5)),
            arm_placebo=ArmEvaluationResult("ARM_B_PLACEBO", s, env, 0.050 + 0.002 * (s % 5)),
            arm_static=ArmEvaluationResult("ARM_C_STATIC", s, env, 0.030)
        )
        trials.append(trial)

    harness = ThreeArmRQCProtocolHarness(n_bootstrap=500, random_seed=42)
    report = harness.evaluate_trials(trials)

    assert report.causality_verified is False
    assert "REFUTED: Delta_informative" in report.summary
    assert "statistically indistinguishable from placebo sham updates" in report.summary


def test_adaptive_advantage_refuted_when_static_rcs_matches_rqc():
    """When static RCS baseline matches RQC, adaptive advantage is refuted."""
    trials = []
    env = _make_envelope()

    for s in range(50):
        # RQC beats placebo, but static RCS is just as good as RQC
        trial = ThreeArmMatchedTrial(
            seed=s,
            arm_rqc=ArmEvaluationResult("ARM_A_RQC", s, env, 0.060),
            arm_placebo=ArmEvaluationResult("ARM_B_PLACEBO", s, env, 0.030),
            arm_static=ArmEvaluationResult("ARM_C_STATIC", s, env, 0.062)
        )
        trials.append(trial)

    harness = ThreeArmRQCProtocolHarness(n_bootstrap=500, random_seed=42)
    report = harness.evaluate_trials(trials)

    assert report.causality_verified is True
    assert report.adaptive_advantage_verified is False
    assert "REFUTED: Delta_adaptive" in report.summary
    assert "Adaptive circuit optimization shows no statistical benefit over static RCS" in report.summary
