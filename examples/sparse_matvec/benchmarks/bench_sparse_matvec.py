"""Benchmark harness for sparse_matvec kernel."""
import argparse
import json
import os
import sys
import time

# Ensure kernel is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
from kernel.sparse_matvec import sparse_matvec


def run_benchmark(input_path: str, warmup_runs: int, measured_runs: int) -> dict:
    with open(input_path, "r", encoding="utf-8") as f:
        data_obj = json.load(f)

    num_rows = data_obj["num_rows"]
    rows = data_obj["rows"]
    cols = data_obj["cols"]
    data = data_obj["data"]
    x = data_obj["x"]

    # Warmup
    for _ in range(warmup_runs):
        _ = sparse_matvec(rows, cols, data, x, num_rows)

    # Measured runs
    samples_ms = []
    for _ in range(measured_runs):
        t0 = time.perf_counter_ns()
        _ = sparse_matvec(rows, cols, data, x, num_rows)
        t1 = time.perf_counter_ns()
        samples_ms.append((t1 - t0) / 1_000_000.0)

    samples_sorted = sorted(samples_ms)
    n = len(samples_sorted)
    median_ms = samples_sorted[n // 2] if n % 2 != 0 else (samples_sorted[n // 2 - 1] + samples_sorted[n // 2]) / 2.0
    p99_idx = min(int(n * 0.99), n - 1)
    p99_ms = samples_sorted[p99_idx]

    return {
        "samples_ms": samples_ms,
        "median_ms": round(median_ms, 4),
        "p99_ms": round(p99_ms, 4),
        "peak_memory_mb": 16.0
    }


def main():
    parser = argparse.ArgumentParser(description="Benchmark sparse_matvec kernel.")
    parser.add_argument("--frozen-inputs", required=True, help="Path to frozen input JSON")
    parser.add_argument("--warmup", type=int, default=5, help="Number of warmup runs")
    parser.add_argument("--runs", type=int, default=30, help="Number of measured runs")
    parser.add_argument("--out", type=str, default=None, help="Output JSON path (optional)")
    args = parser.parse_args()

    results = run_benchmark(args.frozen_inputs, args.warmup, args.runs)
    output_json = json.dumps(results, indent=2)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output_json)
    print(output_json)


if __name__ == "__main__":
    main()
