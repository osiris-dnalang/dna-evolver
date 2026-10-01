"""Reference correctness test suite for sparse_matvec."""
import math
import sys
import os

# Ensure kernel is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))
from kernel.sparse_matvec import sparse_matvec


def test_identity_matrix():
    # 3x3 identity matrix
    rows = [0, 1, 2]
    cols = [0, 1, 2]
    data = [1.0, 1.0, 1.0]
    x = [2.5, -1.0, 4.0]
    y = sparse_matvec(rows, cols, data, x, 3)
    assert len(y) == 3
    for a, b in zip(y, x):
        assert math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)


def test_zero_vector():
    rows = [0, 1]
    cols = [1, 0]
    data = [5.0, 10.0]
    x = [0.0, 0.0]
    y = sparse_matvec(rows, cols, data, x, 2)
    assert y == [0.0, 0.0]


def test_known_dense_equivalent():
    # Matrix:
    # [[1.0, 2.0],
    #  [0.0, 3.0]]
    # x = [4.0, 5.0]
    # y = [1*4 + 2*5, 3*5] = [14.0, 15.0]
    rows = [0, 0, 1]
    cols = [0, 1, 1]
    data = [1.0, 2.0, 3.0]
    x = [4.0, 5.0]
    y = sparse_matvec(rows, cols, data, x, 2)
    assert math.isclose(y[0], 14.0, rel_tol=1e-9)
    assert math.isclose(y[1], 15.0, rel_tol=1e-9)


def test_empty_matrix():
    y = sparse_matvec([], [], [], [1.0, 2.0], 2)
    assert y == [0.0, 0.0]
