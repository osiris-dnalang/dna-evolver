"""Unit tests for Path and Patch Scope Firewall."""
import pytest
from src.validate_contract import load_contract
from src.validate_patch_scope import validate_patch_scope


@pytest.fixture
def contract():
    return load_contract("examples/sparse_matvec_contract.yaml")


def test_allowed_patch_scope(contract):
    with open("examples/allowed_patch.diff", "r", encoding="utf-8") as f:
        patch = f.read()
    res = validate_patch_scope(patch, contract)
    assert res["allowed"] is True
    assert res["reason_code"] == "SCOPE_VALID"


def test_immutable_test_path_denied(contract):
    with open("examples/denied_evaluator_tampering.diff", "r", encoding="utf-8") as f:
        patch = f.read()
    res = validate_patch_scope(patch, contract)
    assert res["allowed"] is False
    assert res["reason_code"] == "IMMUTABLE_PATH_MODIFIED"


def test_immutable_policy_path_denied(contract):
    patch = "--- policy/rules.yaml\n+++ policy/rules.yaml\n@@ -1 +1 @@\n-deny\n+allow\n"
    res = validate_patch_scope(patch, contract)
    assert res["allowed"] is False
    assert res["reason_code"] == "IMMUTABLE_PATH_MODIFIED"


def test_path_traversal_denied(contract):
    patch = "--- a/../secret.env\n+++ b/../secret.env\n@@ -1 +1 @@\n-a\n+b\n"
    res = validate_patch_scope(patch, contract)
    assert res["allowed"] is False
    assert "PATH_TRAVERSAL" in res["reason_code"]


def test_absolute_path_denied(contract):
    patch = "--- /etc/passwd\n+++ /etc/passwd\n@@ -1 +1 @@\n-root\n+hacked\n"
    res = validate_patch_scope(patch, contract)
    assert res["allowed"] is False
    assert "PATH_NOT_NORMALIZED" in res["reason_code"]


def test_excess_files_budget_denied(contract):
    patch = (
        "--- src/kernel/sparse_matvec.py\n+++ src/kernel/sparse_matvec.py\n@@ -1 +1 @@\n-#\n+#\n"
        "--- src/kernel/f2.py\n+++ src/kernel/f2.py\n@@ -1 +1 @@\n-#\n+#\n"
        "--- src/kernel/f3.py\n+++ src/kernel/f3.py\n@@ -1 +1 @@\n-#\n+#\n"
    )
    res = validate_patch_scope(patch, contract)
    assert res["allowed"] is False
    assert res["reason_code"] == "TOO_MANY_FILES_CHANGED"
