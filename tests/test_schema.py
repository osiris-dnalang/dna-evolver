"""Unit tests for DNA-Lang Evolver Contract Schema validation."""
import copy
import pytest
from src.validate_contract import load_contract, validate_contract


@pytest.fixture
def valid_contract_dict():
    return load_contract("examples/sparse_matvec_contract.yaml")


def test_valid_contract_passes(valid_contract_dict):
    valid, errors = validate_contract(valid_contract_dict)
    assert valid, f"Expected valid contract, got errors: {errors}"
    assert len(errors) == 0


def test_reject_raw_shell_command_string(valid_contract_dict):
    c = copy.deepcopy(valid_contract_dict)
    # Replaces argv array with raw shell string
    c["correctness"]["argv"] = "pytest tests/reference"
    valid, errors = validate_contract(c)
    assert not valid
    assert any("argv" in err for err in errors)


def test_reject_unauthorized_authority_enum(valid_contract_dict):
    c = copy.deepcopy(valid_contract_dict)
    # Attempting to grant CANARY or AUTOMATIC_PASS authority
    c["authority"]["sandbox_execution"] = "AUTOMATIC_PASS"
    valid, errors = validate_contract(c)
    assert not valid
    assert any("sandbox_execution" in err for err in errors)


def test_reject_customer_claim_allowed(valid_contract_dict):
    c = copy.deepcopy(valid_contract_dict)
    c["authority"]["customer_claim_allowed"] = True
    valid, errors = validate_contract(c)
    assert not valid
    assert any("customer_claim_allowed" in err for err in errors)


def test_reject_missing_seed(valid_contract_dict):
    c = copy.deepcopy(valid_contract_dict)
    del c["seed"]
    valid, errors = validate_contract(c)
    assert not valid
    assert any("seed" in err for err in errors)
