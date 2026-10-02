"""Sprint Q1: Three-Arm Resource-Matched RQC Verification Protocol.

Disentangles closed-loop feedback from circuit depth drift and parameter mutation artifacts.
Enforces strict resource-matching invariants across:
  - Arm A: RQC Informative Feedback (treatment)
  - Arm B: Placebo / Sham Feedback (matched parameter mutation, non-informative feedback)
  - Arm C: Static RCS (frozen non-adaptive baseline)

Governing Invariant:
If Delta_informative = F_RQC - F_Placebo <= 0, feedback is NOT causal.
If Delta_adaptive = F_RQC - F_Static <= 0, adaptive search has no advantage over static baseline.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple
import numpy as np


def _canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_canonical(data: Any) -> str:
    return hashlib.sha256(_canonical_json(data).encode("utf-8")).hexdigest()


class ResourceDisparityError(ValueError):
    """Raised when experimental arms violate strict resource matching."""
    pass


class CausalityRefutedError(RuntimeError):
    """Raised when active feedback fails to outperform matched placebo or static baseline."""
    pass


@dataclass(frozen=True)
class CircuitResourceEnvelope:
    """Rigorous resource accounting for a single experimental circuit run."""
    seed: int
    num_qubits: int
    qubit_indices: Tuple[int, ...]
    compiled_depth: int
    two_qubit_gate_count: int
    two_qubit_gate_name: str
    single_qubit_gate_count: int
    transpiler_optimization_level: int
    transpiler_version: str
    shot_count: int
    error_mitigation_policy: str

    def assert_matched_with(self, other: CircuitResourceEnvelope, arm_name: str, other_name: str) -> None:
        """Enforces zero disparity across all physical resource dimensions."""
        if self.num_qubits != other.num_qubits or self.qubit_indices != other.qubit_indices:
            raise ResourceDisparityError(
                f"Qubit allocation disparity between {arm_name} and {other_name}: "
                f"{self.qubit_indices} vs {other.qubit_indices}"
            )
        if self.compiled_depth != other.compiled_depth:
            raise ResourceDisparityError(
                f"Compiled depth disparity between {arm_name} ({self.compiled_depth}) and "
                f"{other_name} ({other.compiled_depth}). Depth drift is forbidden."
            )
        if self.two_qubit_gate_count != other.two_qubit_gate_count:
            raise ResourceDisparityError(
                f"Two-qubit gate count disparity between {arm_name} ({self.two_qubit_gate_count}) and "
                f"{other_name} ({other.two_qubit_gate_count})"
            )
        if self.two_qubit_gate_name != other.two_qubit_gate_name:
            raise ResourceDisparityError(
                f"Two-qubit gate family mismatch between {arm_name} ({self.two_qubit_gate_name}) and "
                f"{other_name} ({other.two_qubit_gate_name})"
            )
        if self.single_qubit_gate_count != other.single_qubit_gate_count:
            raise ResourceDisparityError(
                f"Single-qubit gate count disparity between {arm_name} ({self.single_qubit_gate_count}) and "
                f"{other_name} ({other.single_qubit_gate_count})"
            )
        if self.transpiler_optimization_level != other.transpiler_optimization_level:
            raise ResourceDisparityError(
                f"Transpilation level mismatch between {arm_name} and {other_name}"
            )
        if self.shot_count != other.shot_count:
            raise ResourceDisparityError(
                f"Shot count disparity between {arm_name} ({self.shot_count}) and {other_name} ({other.shot_count})"
            )
        if self.error_mitigation_policy != other.error_mitigation_policy:
            raise ResourceDisparityError(
                f"Error mitigation policy mismatch: '{self.error_mitigation_policy}' vs '{other.error_mitigation_policy}'"
            )


@dataclass
class ArmEvaluationResult:
    """Measured outcome for an arm on a matched base-circuit seed."""
    arm_id: str  # 'ARM_A_RQC', 'ARM_B_PLACEBO', 'ARM_C_STATIC'
    seed: int
    resource_envelope: CircuitResourceEnvelope
    fidelity_xeb: float
    measured_shots: List[str] = field(default_factory=list)
    raw_probabilities: Dict[str, float] = field(default_factory=dict)


@dataclass
class ThreeArmMatchedTrial:
    """A matched triplet of circuit runs evaluated under identical conditions."""
    seed: int
    arm_rqc: ArmEvaluationResult
    arm_placebo: ArmEvaluationResult
    arm_static: ArmEvaluationResult

    def validate_resource_matching(self) -> None:
        """Verifies strict pairwise equivalence among all three arms."""
        self.arm_rqc.resource_envelope.assert_matched_with(
            self.arm_placebo.resource_envelope, "RQC_Arm", "Placebo_Arm"
        )
        self.arm_rqc.resource_envelope.assert_matched_with(
            self.arm_static.resource_envelope, "RQC_Arm", "Static_Arm"
        )

    @property
    def delta_informative(self) -> float:
        """Delta_informative = F_RQC - F_Placebo.
        
        Isolates whether the telemetry feedback stream is causal.
        """
        return self.arm_rqc.fidelity_xeb - self.arm_placebo.fidelity_xeb

    @property
    def delta_adaptive(self) -> float:
        """Delta_adaptive = F_RQC - F_Static.
        
        Isolates whether adaptation provides benefit over a frozen baseline.
        """
        return self.arm_rqc.fidelity_xeb - self.arm_static.fidelity_xeb


@dataclass
class ThreeArmExperimentReport:
    """Statistical synthesis of 3-arm matched evaluation across seeds."""
    protocol_version: str
    total_seeds: int
    mean_fidelity_rqc: float
    mean_fidelity_placebo: float
    mean_fidelity_static: float
    delta_informative_mean: float
    delta_informative_ci_99: Tuple[float, float]
    delta_adaptive_mean: float
    delta_adaptive_ci_99: Tuple[float, float]
    causality_verified: bool
    adaptive_advantage_verified: bool
    summary: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "total_seeds": self.total_seeds,
            "mean_fidelity_rqc": round(self.mean_fidelity_rqc, 6),
            "mean_fidelity_placebo": round(self.mean_fidelity_placebo, 6),
            "mean_fidelity_static": round(self.mean_fidelity_static, 6),
            "delta_informative_mean": round(self.delta_informative_mean, 6),
            "delta_informative_ci_99": [
                round(self.delta_informative_ci_99[0], 6),
                round(self.delta_informative_ci_99[1], 6)
            ],
            "delta_adaptive_mean": round(self.delta_adaptive_mean, 6),
            "delta_adaptive_ci_99": [
                round(self.delta_adaptive_ci_99[0], 6),
                round(self.delta_adaptive_ci_99[1], 6)
            ],
            "causality_verified": self.causality_verified,
            "adaptive_advantage_verified": self.adaptive_advantage_verified,
            "summary": self.summary
        }

    def report_sha256(self) -> str:
        return _sha256_canonical(self.to_dict())


class ThreeArmRQCProtocolHarness:
    """Execution and validation harness for 3-arm resource-matched RQC."""

    def __init__(
        self,
        n_bootstrap: int = 1000,
        random_seed: int = 42,
        protocol_version: str = "rqc_3arm_v4.2.1"
    ):
        self.n_bootstrap = n_bootstrap
        self.random_seed = random_seed
        self.protocol_version = protocol_version

    def evaluate_trials(self, trials: Sequence[ThreeArmMatchedTrial]) -> ThreeArmExperimentReport:
        """Validates resource matching for every trial and computes hierarchical bootstrap CIs."""
        if not trials:
            raise ValueError("No trials provided for 3-arm evaluation")

        # 1. Strict Resource Invariant Check on every single trial
        for t in trials:
            t.validate_resource_matching()

        deltas_info = np.array([t.delta_informative for t in trials], dtype=np.float64)
        deltas_adapt = np.array([t.delta_adaptive for t in trials], dtype=np.float64)
        f_rqc = np.array([t.arm_rqc.fidelity_xeb for t in trials], dtype=np.float64)
        f_placebo = np.array([t.arm_placebo.fidelity_xeb for t in trials], dtype=np.float64)
        f_static = np.array([t.arm_static.fidelity_xeb for t in trials], dtype=np.float64)

        rng = np.random.default_rng(self.random_seed)
        n = len(trials)

        # 2. Hierarchical Paired Bootstrap for 99% CI
        boot_info = np.empty(self.n_bootstrap, dtype=np.float64)
        boot_adapt = np.empty(self.n_bootstrap, dtype=np.float64)

        for b in range(self.n_bootstrap):
            idx = rng.integers(0, n, size=n)
            boot_info[b] = np.mean(deltas_info[idx])
            boot_adapt[b] = np.mean(deltas_adapt[idx])

        ci_info_lower = float(np.percentile(boot_info, 0.5))
        ci_info_upper = float(np.percentile(boot_info, 99.5))

        ci_adapt_lower = float(np.percentile(boot_adapt, 0.5))
        ci_adapt_upper = float(np.percentile(boot_adapt, 99.5))

        # 3. Decision Gates:
        # Causal Feedback: Lower bound of 99% CI of Delta_informative must be strictly > 0
        causality_verified = bool(ci_info_lower > 0.0)

        # Adaptive Advantage: Lower bound of 99% CI of Delta_adaptive must be strictly > 0
        adaptive_advantage_verified = bool(ci_adapt_lower > 0.0)

        if causality_verified and adaptive_advantage_verified:
            summary = "PASSED: Feedback causality and adaptive advantage statistically confirmed at 99% CI."
        elif not causality_verified:
            summary = (
                f"REFUTED: Delta_informative 99% CI [{ci_info_lower:.6f}, {ci_info_upper:.6f}] <= 0. "
                "Feedback signal is non-causal (statistically indistinguishable from placebo sham updates)."
            )
        else:
            summary = (
                f"REFUTED: Delta_adaptive 99% CI [{ci_adapt_lower:.6f}, {ci_adapt_upper:.6f}] <= 0. "
                "Adaptive circuit optimization shows no statistical benefit over static RCS baseline."
            )

        return ThreeArmExperimentReport(
            protocol_version=self.protocol_version,
            total_seeds=n,
            mean_fidelity_rqc=float(np.mean(f_rqc)),
            mean_fidelity_placebo=float(np.mean(f_placebo)),
            mean_fidelity_static=float(np.mean(f_static)),
            delta_informative_mean=float(np.mean(deltas_info)),
            delta_informative_ci_99=(ci_info_lower, ci_info_upper),
            delta_adaptive_mean=float(np.mean(deltas_adapt)),
            delta_adaptive_ci_99=(ci_adapt_lower, ci_adapt_upper),
            causality_verified=causality_verified,
            adaptive_advantage_verified=adaptive_advantage_verified,
            summary=summary
        )
