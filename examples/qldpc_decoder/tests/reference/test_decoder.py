"""Reference correctness test suite for qLDPC Min-Sum decoder."""
import json
import os
import sys
import numpy as np

# Ensure kernel is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))
from kernel.minsum_decoder import minsum_decode


def load_dataset():
    data_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../benchmarks/frozen_inputs/qldpc_syndromes_n72.json")
    )
    with open(data_path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_zero_syndrome():
    data = load_dataset()
    H = data["H_dense"]
    m = data["m"]
    n = data["n"]
    zero_s = [0] * m

    e_hat, converged, iters = minsum_decode(zero_s, H, max_iter=10)
    assert converged is True
    assert e_hat == [0] * n


def test_single_qubit_errors():
    data = load_dataset()
    H = np.array(data["H_dense"], dtype=np.uint8)
    m, n = H.shape

    # Test 5 distinct single-qubit errors
    for q in [0, 5, 12, 35, 71]:
        e_true = np.zeros(n, dtype=np.uint8)
        e_true[q] = 1
        s = (H @ e_true) % 2

        e_hat, converged, iters = minsum_decode(s.tolist(), H.tolist(), max_iter=15)
        # Verify syndrome satisfaction
        syn_hat = (H @ np.array(e_hat, dtype=np.uint8)) % 2
        assert np.array_equal(syn_hat, s), f"Syndrome unsatisfied for qubit {q}"
        assert e_hat == e_true.tolist(), f"Failed exact decode for qubit {q}"


def test_frozen_syndrome_batch_satisfaction():
    data = load_dataset()
    H = np.array(data["H_dense"], dtype=np.uint8)
    syndromes = data["syndromes"][:10]  # First 10 frozen syndromes

    success_count = 0
    for s in syndromes:
        e_hat, converged, iters = minsum_decode(s, H.tolist(), max_iter=20)
        syn_hat = (H @ np.array(e_hat, dtype=np.uint8)) % 2
        if np.array_equal(syn_hat, s):
            success_count += 1

    # At least 90% must satisfy syndrome on low-weight errors
    assert success_count >= 9, f"Only {success_count}/10 syndromes satisfied"
