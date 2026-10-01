# DNA-Lang Evolver: Threat Model & Security Posture

## 1. System Mission & Boundary

DNA-Lang Evolver serves as the **policy- and provenance-native contract layer for evolutionary AI coding agents**.

In an evolutionary AI coding pipeline:
$$\text{Gemini proposes} \rightarrow \text{DNA-Lang validates and constrains} \rightarrow \text{sandbox evaluates} \rightarrow \text{OCCR authorizes} \rightarrow \text{human promotes}$$

The AI model (e.g., Gemini / ADK) generates candidate mutations and optimization ideas. It is treated as an **untrusted proposer**. It must **never** possess authority to merge, deploy, modify evaluators, alter policy bundles, access credentials, or dispatch consequential workloads.

---

## 2. Threat Vectors & Defense Invariants

### Threat 1: Evaluator Tampering (Goodharting & Benchmark Invalidation)
* **Attack Scenario**: The model attempts to modify test assertions (`assert True`), delete edge cases, shrink benchmark matrix inputs, or hardcode canned benchmark timing values to make a failing or slow candidate appear successful.
* **Defense**:
  - **Immutable Path Firewall**: Paths matching `tests/reference/**`, `evaluator/**`, `benchmarks/frozen_inputs/**`, `policy/**`, and build configs are declared immutable.
  - **Cryptographic Pinned Hashes**: Contracts pin `reference_tests_tree_sha256` and `benchmark_input_manifest_sha256`. The runner re-verifies these digests against on-disk files before launching evaluation.
  - **Read-Only Source Mounting**: Reference test files are mounted read-only in execution environments.

### Threat 2: Capability Escalation & Data Exfiltration
* **Attack Scenario**: The candidate introduces network imports (`socket`, `requests`, `urllib`), system command execution (`os.system`, `subprocess.Popen`), dynamic evaluation (`eval`, `exec`), or reflection (`getattr`, `globals()`, `locals()`) to exfiltrate secrets or establish persistent host access.
* **Defense**:
  - **AST Semantic Firewall**: Scans the candidate's Abstract Syntax Tree prior to execution.
  - **Prohibited Imports**: Rejects any `ast.Import` or `ast.ImportFrom` not already present in the parent source tree.
  - **Prohibited Calls**: AST visitor intercepts and rejects forbidden identifiers (`eval`, `exec`, `compile`, `open`, `system`, `popen`, `run`, `socket`, `connect`).
  - **Execution Isolation**: Evaluator contracts mandate `network: DENY` and ephemeral temporary workspaces.

### Threat 3: Authority Creep & Automatic Deployment
* **Attack Scenario**: The candidate or an orchestrator attempts to bypass review by asserting canary rights, automatic merge privileges, or production claim authority.
* **Defense**:
  - **Separation of Concerns**: $\text{fitness} \ne \text{authority} \ne \text{release}$. Passing correctness and performance tests never implies authorization to release.
  - **Strict Schema Enums**: The contract schema strictly restricts:
    - `candidate_status`: `PROPOSAL_ONLY`
    - `source_merge`: `HUMAN_APPROVAL_REQUIRED`
    - `deployment`: `BLOCKED`
    - `customer_claim_allowed`: `false`
  - Rejection of invalid authority enums (e.g. `AUTOMATIC_PASS`, `CANARY`) at schema validation time.

### Threat 4: Path Traversal & Scope Smuggling
* **Attack Scenario**: Patch diff headers include `../` relative traversals, absolute `/` paths, windows-style `\` paths, binary blobs, symlink modifications, or touch excessive numbers of files to obfuscate backdoors.
* **Defense**:
  - **Path Normalization**: Rejects any path containing `..`, leading `/`, or `\`.
  - **Budget Enforcements**: Strict caps on `max_files_changed` (e.g., 2 files), `max_patch_bytes` (e.g., 32 KB), and `max_ast_nodes_changed` (e.g., 80 nodes).
  - **Binary & Symlink Rejection**: Diff headers with `GIT binary patch` or symlink mode changes (`120000`) fail immediately.

### Threat 5: Statistical Noise & False Convergence
* **Attack Scenario**: Unstable host conditions or measurement jitter produce an illusory speedup on a single iteration, leading to retention of regressed or unstable candidates.
* **Defense**:
  - **Paired Bootstrap Confidence Intervals**: Resamples paired benchmark observations $B=2000$ times.
  - **Upper Bound Invariant**: Requires that the upper bound of the 99% bootstrap confidence interval for the candidate-to-baseline latency ratio is strictly $< 1.0$.
  - **Tail & Memory Regression Bounds**: Evaluates candidate against strict p99 latency regression limits ($\le 2.0\%$) and memory regression limits ($\le 5.0\%$).

---

## 3. Cryptographic Provenance & Evidence

Every candidate evaluation produces a canonical `dna.evidence_record/v1` document:
- Formatted via deterministic canonical JSON (`OSIRIS-CANONICAL-JSON-V1`).
- Contains SHA-256 digests of base commit, contract, patch, AST diff, test output, benchmark raw samples, and host environment manifest.
- Lineage Merkle root binds the candidate to its parent and experimental lineage.
