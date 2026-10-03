# DNA-Lang Evolver

> **DNA-Lang is the policy- and provenance-native specification layer for evolutionary AI coding systems.**

DNA-Lang provides a typed contract, static capability firewall, hermetic evaluator, and cryptographic evidence ledger for AI-driven code optimization. It enables LLMs (such as Google Gemini via Agent Development Kit) to propose algorithmic code mutations, while ensuring that deterministic evaluators, policy gates, and provenance controls govern what may execute, be retained, or be released.

---

## Architecture & Governance Pipeline

```text
┌─────────────────────────────────────────────────────────────┐
│ Gemini / ADK                                                │
│ - Reads task specification and evaluator feedback           │
│ - Proposes a typed DNA-Lang CandidateProposal               │
│ - Never receives deployment or policy-write credentials     │
└───────────────────────┬─────────────────────────────────────┘
                        │ structured proposal only
                        ▼
┌─────────────────────────────────────────────────────────────┐
│ DNA-Lang Contract Layer                                     │
│ - Validates schema, lineage, mutation scope, AST constraints│
│ - Pins seed commit, mutable paths, evaluator version        │
│ - Rejects unsafe or unverifiable candidates                 │
└───────────────────────┬─────────────────────────────────────┘
                        │ valid candidate artifact
                        ▼
┌─────────────────────────────────────────────────────────────┐
│ OCCR Governance Gate                                        │
│ - Checks actor, role, task scope, budget, expiry, policy    │
│ - Writes authorization receipt before evaluation            │
│ - Grants only sandbox-evaluation capability                 │
└───────────────────────┬─────────────────────────────────────┘
                        │ short-lived execution grant
                        ▼
┌─────────────────────────────────────────────────────────────┐
│ Cloud Run Sandbox / Local Hermetic Runner                   │
│ - Applies patch in an ephemeral workspace                   │
│ - Runs frozen build, tests, benchmarks, static analysis     │
│ - No ambient secrets, no policy mutation, no default egress │
└───────────────────────┬─────────────────────────────────────┘
                        │ measured result + logs + artifact hashes
                        ▼
┌─────────────────────────────────────────────────────────────┐
│ Evidence + Evolution Registry                               │
│ - Stores fitness, failures, lineage, environment digest     │
│ - Retains only evaluator-valid candidates                   │
│ - Keeps release authority separate from fitness             │
└─────────────────────────────────────────────────────────────┘
```

The fundamental invariant is:
$$\text{Gemini proposes} \rightarrow \text{DNA-Lang constrains} \rightarrow \text{evaluators measure} \rightarrow \text{OCCR authorizes} \rightarrow \text{human promotes}$$

---

## Four Demonstrated Foundational Outcomes

The test suite (`tests/test_demo_four_outcomes.py`) demonstrates four distinct, deterministic outcomes:

| Outcome | Candidate | Pipeline Stage | Result | Authority Decision |
|---|---|---|---|---|
| **1. Safe Optimization** | Loop unrolling / tuple unpacking | Hermetic Benchmark | **RETAINED_FOR_REVIEW** (53% speedup, 99% bootstrap CI upper bound < 1.0) | `HOLD` (Human review required) |
| **2. Evaluator Tampering** | Attempting to edit `tests/reference/` | Path Scope Firewall | **DENIED_BY_PATH_FIREWALL** (`IMMUTABLE_PATH_MODIFIED`) | Execution denied |
| **3. Unsafe Capability** | Attempting `import socket` / `os.system` | AST Semantic Firewall | **DENIED_BY_AST_FIREWALL** (`PROHIBITED_CAPABILITY`) | Execution denied |
| **4. Insignificant Speedup** | Trivial comment / whitespace tweak | Hermetic Benchmark | **EVALUATED_NOT_RETAINED** (Correctness passes, but $\Delta < 5\%$ or CI upper bound $\ge 1.0$) | `DENY` |

---

## Directory Structure

```text
dna-evolver/
├── schemas/
│   └── dna.evolver_contract.v1.schema.json    # Formal JSON Schema (Draft 2020-12)
├── examples/
│   ├── sparse_matvec_contract.yaml            # Pinned contract for sparse kernel optimization
│   ├── allowed_patch.diff                     # Safe candidate (53% speedup)
│   ├── denied_evaluator_tampering.diff        # Tampering candidate (touches tests)
│   ├── denied_unsafe_import.diff              # Capability leak candidate (socket/os)
│   ├── insignificant_patch.diff               # Trivial candidate (<5% speedup)
│   └── sparse_matvec/                         # Target benchmark package
│       ├── src/kernel/sparse_matvec.py        # Baseline kernel implementation
│       ├── tests/reference/                   # Reference correctness suite
│       └── benchmarks/                        # Frozen inputs and timing harness
├── src/
│   ├── validate_contract.py                   # Schema validator
│   ├── validate_patch_scope.py                # Path firewall and budget enforcer
│   ├── validate_ast.py                        # AST parser and capability firewall
│   ├── run_hermetic_evaluator.py              # Ephemeral workspace runner & bootstrap CI
│   ├── emit_evidence_receipt.py               # Canonical JSON cryptographic ledger emitter
│   └── cli.py                                 # Unified command line tool
├── tests/
│   ├── test_schema.py                         # Contract schema invariants
│   ├── test_path_firewall.py                  # Path traversal, budget, and immutable rules
│   ├── test_ast_firewall.py                   # Prohibited imports, calls, and symbol bounds
│   ├── test_evaluator_integrity.py            # Hash pinning and correctness gates
│   ├── test_evidence_receipt.py               # Canonical JSON and Merkle root tests
│   └── test_demo_four_outcomes.py             # The 4 foundational outcomes E2E
├── THREAT_MODEL.md                            # Comprehensive security and attack vector model
├── LIMITATIONS.md                             # Boundaries, scope discipline, and non-claims
├── README.md                                  # Package documentation
└── LICENSE                                    # Apache License 2.0
```

---

## Quickstart

### 1. Run the Test Suite
```bash
pytest tests/ -v
```

### 2. Validate a Contract
```bash
python3 -m src.cli check-contract examples/sparse_matvec_contract.yaml
```

### 3. Evaluate a Candidate Patch
```bash
python3 -m src.cli run \
  --contract examples/sparse_matvec_contract.yaml \
  --patch examples/allowed_patch.diff \
  --repo examples/sparse_matvec
```

---

## Google Cloud & Research Alignment

DNA-Lang integrates as a **portable contract and governance layer** alongside Google developer and agent infrastructure:

| Google Capability | DNA-Lang Integration Role |
|---|---|
| **Gemini / AlphaEvolve** | Candidate-generation substrate proposing typed `.diff` mutations |
| **Agent Development Kit (ADK)** | Orchestrates agent tool calls constrained by DNA-Lang contracts |
| **Cloud Run** | Isolated, containerized evaluator runner (`network: DENY`, `--no-traffic`) |
| **Cloud Build** | Reproducible build and hermetic test runner |
| **Artifact Registry** | Stores versioned, frozen evaluator container images and input digests |
| **Cloud Storage** | Long-term evidence artifact store and audit retention target |
| **BigQuery** | Searchable evidence, fitness telemetry, and lineage analytics |

---

## License

Apache License 2.0 -- see [LICENSE](LICENSE). Copyright 2026 Devin Phillip Davis.
