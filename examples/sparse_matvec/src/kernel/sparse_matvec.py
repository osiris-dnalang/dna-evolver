"""Sparse Matrix-Vector Multiplication Kernel (Baseline)."""
from typing import List


def sparse_matvec(rows: List[int], cols: List[int], data: List[float], x: List[float], num_rows: int) -> List[float]:
    """Compute y = A * x where A is in Coordinate (COO) format.
    
    Baseline implementation: uses repeated index lookups in a naive loop.
    """
    y = [0.0] * num_rows
    n_entries = len(data)
    for i in range(n_entries):
        r = rows[i]
        c = cols[i]
        val = data[i]
        y[r] = y[r] + val * x[c]
    return y
