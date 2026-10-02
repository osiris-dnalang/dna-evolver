"""Sprint Q0: Backend Truthfulness Guard.

Enforces zero silent mock/simulator fallbacks and prohibits promoting
simulated or mock data to physical hardware evidence status.

Invariants:
1. Backend identity must be explicit (e.g., 'ibm_brisbane', 'aer_simulator', 'mock_qpu').
2. Simulator fallback must be explicit (no silent fallback).
3. Mock execution must be unmistakable.
4. Evidence must not be promoted from simulation to hardware.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import hashlib
import json


class BackendClass(str, Enum):
    PHYSICAL_HARDWARE = "PHYSICAL_HARDWARE"
    SIMULATOR = "SIMULATOR"
    MOCK = "MOCK"
    SYNTHETIC_STUB = "SYNTHETIC_STUB"


class ClaimLevel(str, Enum):
    THEORETICAL = "THEORETICAL"
    SIMULATION_VERIFIED = "SIMULATION_VERIFIED"
    HARDWARE_OBSERVED = "HARDWARE_OBSERVED"
    PRODUCTION_CERTIFIED = "PRODUCTION_CERTIFIED"


class TruthViolationCode(str, Enum):
    UNSPECIFIED_BACKEND = "UNSPECIFIED_BACKEND"
    UNANNOUNCED_SIMULATOR_FALLBACK = "UNANNOUNCED_SIMULATOR_FALLBACK"
    MOCK_DISGUISED_AS_SIMULATOR = "MOCK_DISGUISED_AS_SIMULATOR"
    SIMULATION_PROMOTION_FORBIDDEN = "SIMULATION_PROMOTION_FORBIDDEN"
    MISSING_EXECUTION_RECEIPT = "MISSING_EXECUTION_RECEIPT"
    BACKEND_MISMATCH = "BACKEND_MISMATCH"


@dataclass
class BackendExecutionManifest:
    backend_id: str
    backend_class: BackendClass
    is_mock: bool
    fallback_occurred: bool = False
    fallback_reason: Optional[str] = None
    requested_backend_id: Optional[str] = None
    execution_receipt_digest: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "backend_id": self.backend_id,
            "backend_class": self.backend_class.value,
            "is_mock": self.is_mock,
            "fallback_occurred": self.fallback_occurred,
            "fallback_reason": self.fallback_reason,
            "requested_backend_id": self.requested_backend_id or self.backend_id,
            "execution_receipt_digest": self.execution_receipt_digest,
            "metadata": self.metadata
        }


@dataclass
class TruthAuditResult:
    valid: bool
    violations: List[Dict[str, str]] = field(default_factory=list)
    effective_claim_ceiling: ClaimLevel = ClaimLevel.THEORETICAL
    manifest_digest: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "violations": self.violations,
            "effective_claim_ceiling": self.effective_claim_ceiling.value,
            "manifest_digest": self.manifest_digest
        }


def audit_backend_truthfulness(
    manifest: BackendExecutionManifest,
    asserted_claim_level: ClaimLevel
) -> TruthAuditResult:
    """Audit an execution manifest against declared claim level.
    
    Blocks any attempt to claim hardware or production evidence using
    simulator or mock backends, and verifies that any fallback was declared.
    """
    violations: List[Dict[str, str]] = []

    # 1. Backend identity must be explicit
    if not manifest.backend_id or manifest.backend_id.strip() == "":
        violations.append({
            "code": TruthViolationCode.UNSPECIFIED_BACKEND.value,
            "message": "Backend ID must be explicitly declared; empty backend identity is prohibited."
        })

    # 2. Simulator fallback must be explicit
    if manifest.requested_backend_id and manifest.requested_backend_id != manifest.backend_id:
        if not manifest.fallback_occurred or not manifest.fallback_reason:
            violations.append({
                "code": TruthViolationCode.UNANNOUNCED_SIMULATOR_FALLBACK.value,
                "message": (
                    f"Execution fell back from requested '{manifest.requested_backend_id}' to "
                    f"'{manifest.backend_id}' without explicit fallback declaration and reason."
                )
            })

    # 3. Mock execution must be unmistakable
    if manifest.backend_class == BackendClass.MOCK and not manifest.is_mock:
        violations.append({
            "code": TruthViolationCode.MOCK_DISGUISED_AS_SIMULATOR.value,
            "message": "Mock backend executed with is_mock=False. Mock status must be unmistakable."
        })

    # 4. Evidence must not be promoted from simulation/mock to hardware
    claim_ceiling = ClaimLevel.THEORETICAL
    if manifest.backend_class == BackendClass.MOCK or manifest.backend_class == BackendClass.SYNTHETIC_STUB:
        claim_ceiling = ClaimLevel.THEORETICAL
        if asserted_claim_level in (ClaimLevel.SIMULATION_VERIFIED, ClaimLevel.HARDWARE_OBSERVED, ClaimLevel.PRODUCTION_CERTIFIED):
            violations.append({
                "code": TruthViolationCode.SIMULATION_PROMOTION_FORBIDDEN.value,
                "message": (
                    f"Mock/stub execution cannot support '{asserted_claim_level.value}'. "
                    f"Maximum allowable claim ceiling is '{claim_ceiling.value}'."
                )
            })
    elif manifest.backend_class == BackendClass.SIMULATOR:
        claim_ceiling = ClaimLevel.SIMULATION_VERIFIED
        if asserted_claim_level in (ClaimLevel.HARDWARE_OBSERVED, ClaimLevel.PRODUCTION_CERTIFIED):
            violations.append({
                "code": TruthViolationCode.SIMULATION_PROMOTION_FORBIDDEN.value,
                "message": (
                    f"Simulator execution cannot support '{asserted_claim_level.value}'. "
                    f"Maximum allowable claim ceiling is '{claim_ceiling.value}'."
                )
            })
    elif manifest.backend_class == BackendClass.PHYSICAL_HARDWARE:
        if not manifest.execution_receipt_digest:
            violations.append({
                "code": TruthViolationCode.MISSING_EXECUTION_RECEIPT.value,
                "message": "Physical hardware claims require an execution_receipt_digest from the QPU provider."
            })
        else:
            claim_ceiling = ClaimLevel.HARDWARE_OBSERVED

    manifest_bytes = json.dumps(manifest.to_dict(), sort_keys=True).encode("utf-8")
    manifest_digest = f"sha256:{hashlib.sha256(manifest_bytes).hexdigest()}"

    return TruthAuditResult(
        valid=(len(violations) == 0),
        violations=violations,
        effective_claim_ceiling=claim_ceiling,
        manifest_digest=manifest_digest
    )
