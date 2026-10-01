# DNA-Lang Evolver: Limitations & Scope Discipline

## 1. Current Architectural Boundaries (Phase 1)

### AST Inspection Language Scope
* The Phase 1 static AST firewall (`src/validate_ast.py`) operates natively on Python syntax trees (`ast` module).
* While the schema permits declaring `rust` or `cpp` as target languages, deep AST semantic capability inspection (e.g., verifying symbol preservation and AST node delta budgets) currently requires language-specific parsers (`syn` for Rust, `libclang` for C++). For non-Python targets, Phase 1 relies on the Path Firewall, byte limits, and hermetic build container isolation.

### Execution Isolation Substrate
* In local development mode (`LOCAL_HERMETIC_RUNNER`), isolation is enforced via ephemeral directory workspaces, `shell=False`, argument list passing, explicit timeouts, and process-level file tracking.
* Local ephemeral execution does not provide Linux kernel cgroup memory limits or network namespace unsharing unless wrapped in Docker, Podman, or gVisor sandbox runtimes. For production environments, the target substrate should be Cloud Run with `--no-traffic`, Cloud Build with isolated worker pools, or gVisor sandbox microVMs.

### Micro-Benchmark Environmental Jitter
* Benchmarking on non-dedicated workstations (e.g. consumer CPUs with dynamic P-core/E-core scheduling, thermal throttling, or background processes) can introduce timing variance.
* DNA-Lang mitigates this using paired bootstrap 99% confidence intervals rather than raw point estimates. However, deterministic micro-benchmarking best practices require fixed-frequency compute instances, pinned CPU affinities, and warmup sweeps.

### Static Taint vs. Dynamic Reflection
* The Phase 1 AST visitor blocks direct calls to dangerous builtins (`eval`, `exec`, `open`, `system`), dangerous imports (`socket`, `requests`, `subprocess`), and reflective introspection (`getattr`, `globals`, `locals`).
* Advanced code obfuscation (e.g. indirect string constructions bypassing symbol tables) is mitigated by the combination of AST node change caps ($\le 80$ nodes) and containerized network isolation (`network: DENY`).

---

## 2. Governance & Non-Authority Invariants

1. **No Autonomous Deployment**: DNA-Lang Evolver is not an autonomous continuous deployment engine. Passing tests and achieving statistical speedups only qualifies a candidate as `RETAINED_FOR_REVIEW`. Promotion, source merges, and deployments strictly require out-of-band human or OCCR policy approval.
2. **No Foundation Model Competition**: DNA-Lang does not train foundation models or generate code itself. It is the contract, policy, evaluation, and evidence harness in which models like Gemini operate safely.
3. **No Unfalsifiable Claims**: Evaluation results are bound to explicit frozen inputs and reference suites. DNA-Lang makes no claims regarding algorithm optimality beyond the pinned benchmark manifest.
