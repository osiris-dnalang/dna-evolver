"""Unified CLI runner for DNA-Lang Evolver."""
import argparse
import json
import os
import sys
from typing import Optional

from src.validate_contract import load_contract, validate_contract
from src.validate_patch_scope import validate_patch_scope
from src.validate_ast import apply_unified_diff, validate_ast
from src.run_hermetic_evaluator import run_hermetic_evaluation
from src.emit_evidence_receipt import emit_evidence_receipt


def run_pipeline(contract_path: str, patch_path: Optional[str], repo_root: str) -> dict:
    """Execute the full end-to-end DNA-Lang evolution pipeline on a candidate patch."""
    # 1. Load and validate contract
    contract = load_contract(contract_path)
    valid, errors = validate_contract(contract)
    if not valid:
        return {
            "status": "REJECTED_CONTRACT_INVALID",
            "errors": errors
        }

    patch_str = None
    if patch_path and os.path.exists(patch_path):
        with open(patch_path, "r", encoding="utf-8") as f:
            patch_str = f.read()

    # 2. Path firewall
    if patch_str:
        scope_res = validate_patch_scope(patch_str, contract)
        if not scope_res["allowed"]:
            receipt = emit_evidence_receipt(
                contract=contract,
                patch_str=patch_str,
                scope_result=scope_res,
                ast_result={"allowed": False, "reason_code": "SKIPPED_DUE_TO_SCOPE_DENIAL"},
                eval_result={"evaluation_executed": False, "retained": False, "fitness_status": "DENIED_BY_PATH_FIREWALL"}
            )
            return {
                "status": "DENIED_BY_PATH_FIREWALL",
                "scope_result": scope_res,
                "evidence_receipt": receipt
            }
    else:
        scope_res = {"allowed": True, "reason_code": "NO_PATCH_PROVIDED"}

    # 3. AST firewall
    orig_kernel_path = os.path.join(repo_root, "src/kernel/sparse_matvec.py")
    if patch_str and os.path.exists(orig_kernel_path):
        with open(orig_kernel_path, "r", encoding="utf-8") as f:
            orig_code = f.read()
        try:
            cand_code = apply_unified_diff(orig_code, patch_str)
            ast_res = validate_ast(orig_code, cand_code, contract)
        except Exception as e:
            ast_res = {"allowed": False, "reason_code": "PATCH_APPLICATION_ERROR", "message": str(e)}

        if not ast_res["allowed"]:
            receipt = emit_evidence_receipt(
                contract=contract,
                patch_str=patch_str,
                scope_result=scope_res,
                ast_result=ast_res,
                eval_result={"evaluation_executed": False, "retained": False, "fitness_status": "DENIED_BY_AST_FIREWALL"}
            )
            return {
                "status": "DENIED_BY_AST_FIREWALL",
                "ast_result": ast_res,
                "evidence_receipt": receipt
            }
    else:
        ast_res = {"allowed": True, "reason_code": "NO_PATCH_OR_KERNEL"}

    # 4. Hermetic Evaluator
    eval_res = run_hermetic_evaluation(repo_root, patch_str, contract)

    # 5. Emit Evidence Record
    receipt = emit_evidence_receipt(
        contract=contract,
        patch_str=patch_str,
        scope_result=scope_res,
        ast_result=ast_res,
        eval_result=eval_res
    )

    final_status = "RETAINED_FOR_REVIEW" if eval_res.get("retained") else "EVALUATED_NOT_RETAINED"
    return {
        "status": final_status,
        "scope_result": scope_res,
        "ast_result": ast_res,
        "evaluation_result": eval_res,
        "evidence_receipt": receipt
    }


def main():
    parser = argparse.ArgumentParser(description="DNA-Lang Evolver CLI")
    subparsers = parser.add_subparsers(dest="command")

    # check-contract
    p_contract = subparsers.add_parser("check-contract", help="Validate evolver contract against schema")
    p_contract.add_argument("contract", help="Path to contract YAML/JSON")

    # run
    p_run = subparsers.add_parser("run", help="Evaluate a candidate patch against a contract")
    p_run.add_argument("--contract", required=True, help="Path to contract YAML")
    p_run.add_argument("--patch", required=True, help="Path to unified diff patch")
    p_run.add_argument("--repo", required=True, help="Path to target repo root")

    args = parser.parse_args()

    if args.command == "check-contract":
        valid, errors = validate_contract(args.contract)
        if valid:
            print(f"Contract {args.contract} is VALID.")
            sys.exit(0)
        else:
            print(f"Contract {args.contract} has errors:\n" + "\n".join(errors))
            sys.exit(1)

    elif args.command == "run":
        res = run_pipeline(args.contract, args.patch, args.repo)
        print(json.dumps(res, indent=2))
        sys.exit(0 if res.get("status") == "RETAINED_FOR_REVIEW" else 1)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
