"""Unit tests for AST Structural and Semantic Capability Firewall."""
import pytest
from src.validate_contract import load_contract
from src.validate_ast import apply_unified_diff, validate_ast


@pytest.fixture
def contract():
    return load_contract("examples/sparse_matvec_contract.yaml")


@pytest.fixture
def orig_source():
    with open("examples/sparse_matvec/src/kernel/sparse_matvec.py", "r", encoding="utf-8") as f:
        return f.read()


def test_allowed_ast_transformation(contract, orig_source):
    with open("examples/allowed_patch.diff", "r", encoding="utf-8") as f:
        patch = f.read()
    cand = apply_unified_diff(orig_source, patch)
    res = validate_ast(orig_source, cand, contract)
    assert res["allowed"] is True
    assert res["reason_code"] == "AST_VALID"
    assert "sparse_matvec" in res["details"]["changed_symbols"]


def test_prohibited_import_denied(contract, orig_source):
    with open("examples/denied_unsafe_import.diff", "r", encoding="utf-8") as f:
        patch = f.read()
    cand = apply_unified_diff(orig_source, patch)
    res = validate_ast(orig_source, cand, contract)
    assert res["allowed"] is False
    assert "PROHIBITED" in res["reason_code"]


def test_prohibited_call_denied(contract, orig_source):
    bad_code = orig_source + "\n# added call\n_ = eval('2+2')\n"
    res = validate_ast(orig_source, bad_code, contract)
    assert res["allowed"] is False
    assert "PROHIBITED_CALL:eval" in res["message"] or res["reason_code"] == "SYMBOL_OUTSIDE_ALLOWED_SCOPE"


def test_unallowed_symbol_modification_denied(contract, orig_source):
    bad_code = orig_source + "\ndef unauthorized_helper():\n    return 100\n"
    res = validate_ast(orig_source, bad_code, contract)
    assert res["allowed"] is False
    assert res["reason_code"] == "SYMBOL_OUTSIDE_ALLOWED_SCOPE"


def test_syntax_error_rejected(contract, orig_source):
    bad_syntax = orig_source + "\ndef broken_syntax(\n"
    res = validate_ast(orig_source, bad_syntax, contract)
    assert res["allowed"] is False
    assert res["reason_code"] == "SYNTAX_INVALID"
