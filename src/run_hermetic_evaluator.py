"""Hermetic Evaluator Runner for DNA-Lang Evolver."""
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple


def compute_file_sha256(path: str) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def compute_paired_bootstrap_ci(
    baseline_samples: List[float],
    candidate_samples: List[float],
    n_resamples: int = 2000,
    confidence_level: float = 0.99
) -> Tuple[float, float]:
    """Compute bootstrap confidence interval for candidate/baseline median ratio."""
    random.seed(20261001)
    ratios = []
    n = min(len(baseline_samples), len(candidate_samples))

    for _ in range(n_resamples):
        b_resample = [random.choice(baseline_samples) for _ in range(n)]
        c_resample = [random.choice(candidate_samples) for _ in range(n)]
        b_med = sorted(b_resample)[n // 2]
        c_med = sorted(c_resample)[n // 2]
        if b_med > 0:
            ratios.append(c_med / b_med)

    ratios.sort()
    alpha = 1.0 - confidence_level
    low_idx = int(alpha / 2.0 * len(ratios))
    high_idx = int((1.0 - alpha / 2.0) * len(ratios))
    return ratios[low_idx], ratios[min(high_idx, len(ratios) - 1)]


def run_hermetic_evaluation(
    repo_root: str,
    patch_str: Optional[str],
    contract: Dict[str, Any]
) -> Dict[str, Any]:
    """Execute evaluation in an isolated ephemeral workspace."""
    eval_cfg = contract.get("evaluator", {})
    correctness_cfg = contract.get("correctness", {})
    perf_cfg = contract.get("performance", {})
    timeout_seconds = eval_cfg.get("resources", {}).get("timeout_seconds", 60.0)

    # 1. Setup ephemeral workspace
    with tempfile.TemporaryDirectory(prefix="dna_eval_") as tmpdir:
        # Copy repository tree into ephemeral workspace
        shutil.copytree(repo_root, tmpdir, dirs_exist_ok=True)

        # 2. Verify evaluator and reference integrity
        ref_tests_path = os.path.join(tmpdir, "tests/reference/test_sparse_matvec.py")
        if os.path.exists(ref_tests_path):
            curr_ref_hash = compute_file_sha256(ref_tests_path)
            expected_ref_hash = eval_cfg.get("reference_tests_tree_sha256")
            if expected_ref_hash and curr_ref_hash != expected_ref_hash:
                return {
                    "evaluation_executed": False,
                    "retained": False,
                    "reason_code": "EVALUATOR_INTEGRITY_COMPROMISED",
                    "message": f"Reference test hash mismatch ({curr_ref_hash} != {expected_ref_hash})",
                    "details": {}
                }

        # 3. Apply patch if provided
        if patch_str:
            patch_path = os.path.join(tmpdir, "candidate.patch")
            with open(patch_path, "w", encoding="utf-8") as f:
                f.write(patch_str)
            apply_res = subprocess.run(
                ["patch", "-p0", "-i", "candidate.patch"],
                cwd=tmpdir,
                shell=False,
                capture_output=True,
                text=True
            )
            if apply_res.returncode != 0:
                return {
                    "evaluation_executed": False,
                    "retained": False,
                    "reason_code": "PATCH_APPLICATION_FAILED",
                    "message": f"Failed to apply patch: {apply_res.stderr}",
                    "details": {"stdout": apply_res.stdout, "stderr": apply_res.stderr}
                }

        # 4. Correctness evaluation
        corr_argv = correctness_cfg.get("argv", ["pytest", "tests/reference"])
        try:
            corr_proc = subprocess.run(
                corr_argv,
                cwd=tmpdir,
                shell=False,
                capture_output=True,
                text=True,
                timeout=correctness_cfg.get("timeout_seconds", 30.0)
            )
        except subprocess.TimeoutExpired:
            return {
                "evaluation_executed": True,
                "correctness_status": "TIMEOUT",
                "retained": False,
                "reason_code": "CORRECTNESS_TIMEOUT",
                "message": "Correctness test execution timed out",
                "details": {}
            }

        expected_exit = correctness_cfg.get("expected_exit_code", 0)
        test_out_hash = hashlib.sha256(
            (corr_proc.stdout + corr_proc.stderr).encode("utf-8")
        ).hexdigest()

        if corr_proc.returncode != expected_exit:
            return {
                "evaluation_executed": True,
                "correctness_status": "FAIL",
                "test_output_hash": f"sha256:{test_out_hash}",
                "retained": False,
                "reason_code": "CORRECTNESS_FAILED",
                "message": f"Correctness tests failed with exit code {corr_proc.returncode}",
                "details": {
                    "exit_code": corr_proc.returncode,
                    "stdout": corr_proc.stdout[:1000],
                    "stderr": corr_proc.stderr[:1000]
                }
            }

        # 5. Performance evaluation (ONLY if correctness passes)
        perf_argv = perf_cfg.get("argv")
        if not perf_argv:
            return {
                "evaluation_executed": True,
                "correctness_status": "PASS",
                "retained": True,
                "reason_code": "CORRECTNESS_ONLY_PASS",
                "message": "Correctness passed; no performance benchmark requested",
                "details": {}
            }

        try:
            perf_proc = subprocess.run(
                perf_argv,
                cwd=tmpdir,
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds
            )
        except subprocess.TimeoutExpired:
            return {
                "evaluation_executed": True,
                "correctness_status": "PASS",
                "performance_status": "TIMEOUT",
                "retained": False,
                "reason_code": "BENCHMARK_TIMEOUT",
                "message": "Benchmark execution exceeded timeout budget",
                "details": {}
            }

        if perf_proc.returncode != 0:
            return {
                "evaluation_executed": True,
                "correctness_status": "PASS",
                "performance_status": "FAIL",
                "retained": False,
                "reason_code": "BENCHMARK_PROCESS_ERROR",
                "message": f"Benchmark command returned error code {perf_proc.returncode}",
                "details": {"stderr": perf_proc.stderr[:1000]}
            }

        try:
            candidate_metrics = json.loads(perf_proc.stdout.strip())
        except Exception as e:
            return {
                "evaluation_executed": True,
                "correctness_status": "PASS",
                "performance_status": "MALFORMED_OUTPUT",
                "retained": False,
                "reason_code": "BENCHMARK_OUTPUT_PARSE_ERROR",
                "message": f"Benchmark stdout did not parse as JSON: {e}",
                "details": {"stdout": perf_proc.stdout[:1000]}
            }

        # 6. Load baseline artifact
        baseline_path = os.path.join(tmpdir, "benchmarks/frozen_inputs/baseline_artifact.json")
        with open(baseline_path, "r", encoding="utf-8") as f:
            baseline_metrics = json.load(f)

        base_samples = baseline_metrics["samples_ms"]
        cand_samples = candidate_metrics["samples_ms"]
        base_med = baseline_metrics["median_ms"]
        cand_med = candidate_metrics["median_ms"]

        # Improvement calculation
        improvement_pct = ((base_med - cand_med) / base_med) * 100.0
        p99_regression_pct = ((candidate_metrics["p99_ms"] - baseline_metrics["p99_ms"]) / baseline_metrics["p99_ms"]) * 100.0
        mem_regression_pct = ((candidate_metrics["peak_memory_mb"] - baseline_metrics["peak_memory_mb"]) / baseline_metrics["peak_memory_mb"]) * 100.0

        ci_low, ci_high = compute_paired_bootstrap_ci(base_samples, cand_samples)

        retain_rules = perf_cfg.get("retain_if", {})
        min_imp = retain_rules.get("minimum_improvement_percent", 5.0)
        max_p99_reg = retain_rules.get("maximum_p99_regression_percent", 2.0)
        max_mem_reg = retain_rules.get("maximum_memory_regression_percent", 5.0)

        # Decision rule:
        # 1. improvement_pct >= min_imp
        # 2. ci_high < 1.0 (statistically significant acceleration at declared CI)
        # 3. p99 regression within bounds
        # 4. memory regression within bounds
        statistically_significant = (ci_high < 1.0)
        meets_threshold = (improvement_pct >= min_imp)
        p99_ok = (p99_regression_pct <= max_p99_reg)
        mem_ok = (mem_regression_pct <= max_mem_reg)

        retained = bool(meets_threshold and statistically_significant and p99_ok and mem_ok)

        bench_samples_hash = hashlib.sha256(
            json.dumps(cand_samples, sort_keys=True).encode("utf-8")
        ).hexdigest()

        return {
            "evaluation_executed": True,
            "correctness_status": "PASS",
            "test_output_hash": f"sha256:{test_out_hash}",
            "benchmark_samples_hash": f"sha256:{bench_samples_hash}",
            "baseline_median_ms": base_med,
            "candidate_median_ms": cand_med,
            "improvement_percent": round(improvement_pct, 2),
            "paired_bootstrap_ci_99": [round(ci_low, 4), round(ci_high, 4)],
            "statistically_significant": statistically_significant,
            "retained": retained,
            "fitness_status": "RETAINED_FOR_REVIEW" if retained else "REJECTED_FITNESS_INSUFFICIENT",
            "reason_code": "PERFORMANCE_THRESHOLD_MET" if retained else "FITNESS_THRESHOLD_NOT_MET",
            "message": (
                f"Candidate achieved {improvement_pct:.2f}% improvement "
                f"(99% CI: [{ci_low:.3f}, {ci_high:.3f}] ratio). Retained: {retained}"
            ),
            "details": {
                "p99_regression_percent": round(p99_regression_pct, 2),
                "memory_regression_percent": round(mem_regression_pct, 2)
            }
        }
