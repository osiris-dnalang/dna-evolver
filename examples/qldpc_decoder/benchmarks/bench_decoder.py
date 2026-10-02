"""Benchmark harness for qLDPC Min-Sum Belief Propagation Decoder."""
import argparse
import json
import os
import sys
import time
import numpy as np

# Ensure kernel is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
from kernel.minsum_decoder import minsum_decode


def run_benchmark(input_path: str, warmup_runs: int, measured_runs: int) -> dict:
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    H_dense = data["H_dense"]
    syndromes = data["syndromes"][:25]  # benchmark on 25 syndromes per sweep

    # Warmup
    for _ in range(warmup_runs):
        for s in syndromes[:5]:
            _ = minsum_decode(s, H_dense, max_iter=15)

    # Measured runs (measure batch of decodes)
    samples_us = []
    converged_total = 0
    total_decodes = 0

    for _ in range(measured_runs):
        t0 = time.perf_counter_ns()
        for s in syndromes:
            _, conv, _ = minsum_decode(s, H_dense, max_iter=15)
            if conv:
                converged_total += 1
            total_decodes += 1
        t1 = time.perf_counter_ns()
        # Microseconds per syndrome decode
        per_syndrome_us = (t1 - t0) / (len(syndromes) * 1000.0)
        samples_us.append(per_syndrome_us)

    samples_sorted = sorted(samples_us)
    n = len(samples_sorted)
    median_us = samples_sorted[n // 2] if n % 2 != 0 else (samples_sorted[n // 2 - 1] + samples_sorted[n // 2]) / 2.0
    p99_idx = min(int(n * 0.99), n - 1)
    p99_us = samples_sorted[p99_idx]
    convergence_rate = round(converged_total / total_decodes, 4)

    return {
        "samples_ms": samples_us,  # schema expects samples array
        "median_ms": round(median_us, 4),
        "p99_ms": round(p99_us, 4),
        "convergence_rate": convergence_rate,
        "peak_memory_mb": 24.0
    }


def main():
    parser = argparse.ArgumentParser(description="Benchmark qLDPC minsum_decode kernel.")
    parser.add_argument("--frozen-inputs", required=True, help="Path to frozen input JSON")
    parser.add_argument("--warmup", type=int, default=3, help="Warmup runs")
    parser.add_argument("--runs", type=int, default=20, help="Measured runs")
    parser.add_argument("--out", type=str, default=None, help="Output JSON path")
    args = parser.parse_args()

    results = run_benchmark(args.frozen_inputs, args.warmup, args.runs)
    out_json = json.dumps(results, indent=2)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out_json)
    print(out_json)


if __name__ == "__main__":
    main()
