"""Tests verifying quarantine firewall and isolation of speculative hypotheses."""
import os
import yaml
import pytest
from src.validate_patch_scope import validate_patch_scope


def test_quarantine_paths_are_immutable():
    """Attempting to patch hypotheses/ is blocked by path firewall."""
    contract = {
        "scope": {
            "mutable_paths": ["src/kernel/**"],
            "immutable_paths": ["evaluator/**", "tests/reference/**", "hypotheses/**"]
        }
    }
    patch_str = (
        "--- hypotheses/crsm_propulsion/CONCEPT_NOTE.md\n"
        "+++ hypotheses/crsm_propulsion/CONCEPT_NOTE.md\n"
        "@@ -1,3 +1,3 @@\n"
        "-# Concept Note\n"
        "+# Tampered Concept Note\n"
    )
    res = validate_patch_scope(patch_str, contract)
    assert not res["allowed"]
    assert res["reason_code"] == "IMMUTABLE_PATH_MODIFIED"


def test_quarantine_records_enforce_no_execution_authority():
    """All quarantine authority yaml records explicitly deny execution and claims."""
    quarantine_dir = "hypotheses"
    authority_files = [
        "crsm_propulsion/NO_EXECUTION_AUTHORITY.yaml",
        "genomic_twin/NO_PATIENT_DATA.yaml",
        "vesta_transport/NO_BUILD_OR_TEST_AUTHORITY.yaml"
    ]
    for rel in authority_files:
        full_p = os.path.join(quarantine_dir, rel)
        assert os.path.exists(full_p), f"Missing {full_p}"
        with open(full_p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        auth = data.get("authorities", {})
        assert data.get("claim_ceiling") == "THEORETICAL"
        assert auth.get("customer_claim_allowed") is False
        assert auth.get("execution_authority", "NONE") == "NONE" or auth.get("operational_execution") == "BLOCKED"
