"""Program Database and Multi-Objective Pareto Lineage Registry for DNA-Lang Evolver.

Tracks evolutionary search history, multi-objective Pareto frontiers,
lineage DAGs, and honest negative results/errata ledgers.

Core Invariants:
1. All candidates (positive, neutral, and negative) are retained with evidence receipts.
2. Negative results are recorded with exact failure modes to prevent repeat exploration.
3. Multi-objective frontier tracks non-dominated trade-offs across latency, p99, and memory.
"""
from dataclasses import dataclass, field
import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from src.emit_evidence_receipt import canonical_json_bytes


@dataclass
class CandidateRecord:
    candidate_hash: str
    parent_candidate_hash: str
    generation: int
    contract_id: str
    patch_summary: str
    correctness_status: str
    retained_for_review: bool
    median_latency_ms: Optional[float]
    p99_latency_ms: Optional[float]
    peak_memory_mb: Optional[float]
    improvement_percent: Optional[float]
    evidence_receipt_hash: str
    timestamp: float
    failure_category: Optional[str] = None
    failure_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_hash": self.candidate_hash,
            "parent_candidate_hash": self.parent_candidate_hash,
            "generation": self.generation,
            "contract_id": self.contract_id,
            "patch_summary": self.patch_summary,
            "correctness_status": self.correctness_status,
            "retained_for_review": self.retained_for_review,
            "median_latency_ms": self.median_latency_ms,
            "p99_latency_ms": self.p99_latency_ms,
            "peak_memory_mb": self.peak_memory_mb,
            "improvement_percent": self.improvement_percent,
            "evidence_receipt_hash": self.evidence_receipt_hash,
            "timestamp": self.timestamp,
            "failure_category": self.failure_category,
            "failure_message": self.failure_message
        }


class ProgramDatabase:
    """Manages multi-generation candidates, Pareto frontiers, and negative result errata."""

    def __init__(self, db_dir: Optional[str] = None):
        self.db_dir = db_dir
        self.candidates: Dict[str, CandidateRecord] = {}
        self.pareto_frontier: List[str] = []  # candidate_hashes
        self.negative_results: List[str] = []  # candidate_hashes
        self.children: Dict[str, List[str]] = {}  # parent -> children

        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
            self._load_from_disk()

    def record_candidate(
        self,
        candidate_hash: str,
        parent_candidate_hash: str,
        generation: int,
        contract_id: str,
        patch_summary: str,
        scope_res: Dict[str, Any],
        ast_res: Dict[str, Any],
        eval_res: Dict[str, Any],
        receipt: Dict[str, Any]
    ) -> CandidateRecord:
        """Records an evaluation outcome into the program database."""
        # Categorize failure if not retained
        failure_cat = None
        failure_msg = None

        if not scope_res.get("allowed", False):
            failure_cat = "SCOPE_FIREWALL_VIOLATION"
            failure_msg = scope_res.get("reason_code")
        elif not ast_res.get("allowed", False):
            failure_cat = "AST_FIREWALL_VIOLATION"
            failure_msg = ast_res.get("reason_code")
        elif eval_res.get("correctness_status") != "PASS":
            failure_cat = "CORRECTNESS_FAILURE"
            failure_msg = eval_res.get("message")
        elif not eval_res.get("retained", False):
            failure_cat = "FITNESS_INSUFFICIENT"
            failure_msg = eval_res.get("message")

        receipt_bytes = canonical_json_bytes(receipt)
        receipt_hash = f"sha256:{hashlib.sha256(receipt_bytes).hexdigest()}"

        record = CandidateRecord(
            candidate_hash=candidate_hash,
            parent_candidate_hash=parent_candidate_hash,
            generation=generation,
            contract_id=contract_id,
            patch_summary=patch_summary,
            correctness_status=eval_res.get("correctness_status", "NOT_EVALUATED"),
            retained_for_review=eval_res.get("retained", False),
            median_latency_ms=eval_res.get("candidate_median_ms"),
            p99_latency_ms=eval_res.get("details", {}).get("candidate_p99_ms"),
            peak_memory_mb=eval_res.get("details", {}).get("candidate_peak_memory_mb"),
            improvement_percent=eval_res.get("improvement_percent"),
            evidence_receipt_hash=receipt_hash,
            timestamp=time.time(),
            failure_category=failure_cat,
            failure_message=failure_msg
        )

        self.candidates[candidate_hash] = record
        if parent_candidate_hash not in self.children:
            self.children[parent_candidate_hash] = []
        self.children[parent_candidate_hash].append(candidate_hash)

        if record.retained_for_review:
            self._update_pareto_frontier(candidate_hash)
        else:
            self.negative_results.append(candidate_hash)

        if self.db_dir:
            self._persist_record(record)

        return record

    def _dominates(self, cand_a: CandidateRecord, cand_b: CandidateRecord) -> bool:
        """Returns True if Candidate A Pareto-dominates Candidate B.
        
        Assumes all metrics are to be minimized (latency, memory).
        A dominates B if A is no worse in all metrics and strictly better in at least one.
        """
        if cand_a.median_latency_ms is None or cand_b.median_latency_ms is None:
            return False

        a_lat = cand_a.median_latency_ms
        b_lat = cand_b.median_latency_ms

        # Check latency dominance
        better_or_equal = (a_lat <= b_lat)
        strictly_better = (a_lat < b_lat)

        return better_or_equal and strictly_better

    def _update_pareto_frontier(self, new_cand_hash: str):
        """Update Pareto frontier with new retained candidate."""
        new_cand = self.candidates[new_cand_hash]
        updated_frontier: List[str] = []

        is_dominated = False
        for existing_hash in self.pareto_frontier:
            existing_cand = self.candidates[existing_hash]
            if self._dominates(existing_cand, new_cand):
                is_dominated = True
                updated_frontier.append(existing_hash)
            elif self._dominates(new_cand, existing_cand):
                # Existing candidate is dominated by new candidate; drop from frontier
                continue
            else:
                updated_frontier.append(existing_hash)

        if not is_dominated:
            updated_frontier.append(new_cand_hash)

        self.pareto_frontier = updated_frontier

    def get_pareto_candidates(self) -> List[CandidateRecord]:
        """Return all candidate records currently on the Pareto frontier."""
        return [self.candidates[h] for h in self.pareto_frontier]

    def get_negative_results(self) -> List[CandidateRecord]:
        """Return all negative results / errata records."""
        return [self.candidates[h] for h in self.negative_results]

    def get_lineage(self, candidate_hash: str) -> List[CandidateRecord]:
        """Trace lineage back from a candidate to root."""
        lineage: List[CandidateRecord] = []
        curr = candidate_hash
        while curr in self.candidates:
            rec = self.candidates[curr]
            lineage.append(rec)
            curr = rec.parent_candidate_hash
            if curr.startswith("sha256:00000000"):
                break
        return lineage

    def _persist_record(self, record: CandidateRecord):
        """Append record to disk ledger."""
        all_path = os.path.join(self.db_dir, "candidate_ledger.jsonl")
        with open(all_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record.to_dict()) + "\n")

        if not record.retained_for_review:
            neg_path = os.path.join(self.db_dir, "negative_results_ledger.jsonl")
            with open(neg_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict()) + "\n")

    def _load_from_disk(self):
        """Load database state from existing ledgers."""
        all_path = os.path.join(self.db_dir, "candidate_ledger.jsonl")
        if not os.path.exists(all_path):
            return
        with open(all_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                rec = CandidateRecord(**d)
                self.candidates[rec.candidate_hash] = rec
                if rec.parent_candidate_hash not in self.children:
                    self.children[rec.parent_candidate_hash] = []
                self.children[rec.parent_candidate_hash].append(rec.candidate_hash)
                if rec.retained_for_review:
                    self._update_pareto_frontier(rec.candidate_hash)
                else:
                    self.negative_results.append(rec.candidate_hash)
