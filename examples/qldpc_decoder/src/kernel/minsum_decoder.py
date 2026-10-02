"""Min-Sum Belief Propagation Decoder for qLDPC Syndrome Decoding (Baseline)."""
from typing import List, Tuple
import numpy as np


def minsum_decode(
    syndrome: List[int],
    H_dense: List[List[int]],
    max_iter: int = 20,
    alpha: float = 0.75,
    prior_llr: float = 3.0
) -> Tuple[List[int], bool, int]:
    """Decode a binary error syndrome on a quantum LDPC check matrix.
    
    Args:
        syndrome: Syndrome vector s of length m (checks).
        H_dense: Binary parity check matrix H of shape (m, n).
        max_iter: Maximum message-passing iterations.
        alpha: Min-Sum normalization scaling factor (default 0.75).
        prior_llr: Log-likelihood ratio for channel error probability.
        
    Returns:
        (estimated_error, converged, iterations_used)
    """
    H = np.asarray(H_dense, dtype=np.uint8)
    s = np.asarray(syndrome, dtype=np.uint8)
    m, n = H.shape

    # Pre-extract neighbor indices for each check and variable
    check_nbrs = [np.nonzero(H[c, :])[0] for c in range(m)]
    var_nbrs = [np.nonzero(H[:, v])[0] for v in range(n)]

    # Initial variable-to-check messages: prior LLR
    # Message dictionaries / matrices:
    # q[v, c]: message from variable v to check c
    # r[c, v]: message from check c to variable v
    q = {}
    r = {}
    for v in range(n):
        for c in var_nbrs[v]:
            q[(v, c)] = prior_llr
            r[(c, v)] = 0.0

    converged = False
    iterations_used = 0

    for it in range(1, max_iter + 1):
        iterations_used = it

        # 1. Check node update (Min-Sum)
        for c in range(m):
            v_list = check_nbrs[c]
            deg = len(v_list)
            for v in v_list:
                # Neighbors of c excluding v
                other_vars = [v_other for v_other in v_list if v_other != v]
                
                # Sign product with syndrome sign (-1)^s[c]
                sign_prod = -1.0 if s[c] == 1 else 1.0
                min_mag = 1e9

                for v_other in other_vars:
                    val = q[(v_other, c)]
                    if val < 0:
                        sign_prod *= -1.0
                    mag = abs(val)
                    if mag < min_mag:
                        min_mag = mag

                r[(c, v)] = alpha * sign_prod * min_mag

        # 2. Variable node update and hard decision
        L_total = np.full(n, prior_llr, dtype=np.float64)
        for v in range(n):
            for c in var_nbrs[v]:
                L_total[v] += r[(c, v)]

        # Hard decision
        e_hat = np.zeros(n, dtype=np.uint8)
        e_hat[L_total < 0] = 1

        # 3. Syndrome check: early termination
        syn_check = (H @ e_hat) % 2
        if np.array_equal(syn_check, s):
            converged = True
            break

        # 4. Update variable-to-check messages for next iteration
        for v in range(n):
            for c in var_nbrs[v]:
                q[(v, c)] = L_total[v] - r[(c, v)]

    return e_hat.tolist(), bool(converged), iterations_used
