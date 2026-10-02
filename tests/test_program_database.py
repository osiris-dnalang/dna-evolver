"""Tests for Program Database, Pareto frontier, and negative results ledger."""
import os
import shutil
import tempfile
import pytest
from src.program_database import ProgramDatabase, CandidateRecord


@pytest.fixture
def temp_db_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d)


def test_record_retained_candidate(temp_db_dir):
    db = ProgramDatabase(db_dir=temp_db_dir)
    rec = db.record_candidate(
        candidate_hash="sha256:cand1",
        parent_candidate_hash="sha256:0000000000000000000000000000000000000000000000000000000000000000",
        generation=1,
        contract_id="contract-test",
        patch_summary="Vectorized inner loop",
        scope_res={"allowed": True},
        ast_res={"allowed": True},
        eval_res={
            "correctness_status": "PASS",
            "retained": True,
            "candidate_median_ms": 1.20,
            "improvement_percent": 15.0
        },
        receipt={"receipt_id": "r1"}
    )
    assert rec.retained_for_review is True
    assert len(db.get_pareto_candidates()) == 1
    assert db.get_pareto_candidates()[0].candidate_hash == "sha256:cand1"
    assert len(db.get_negative_results()) == 0


def test_pareto_dominance(temp_db_dir):
    db = ProgramDatabase(db_dir=temp_db_dir)
    # Cand 1: 1.20 ms
    db.record_candidate(
        candidate_hash="sha256:cand1",
        parent_candidate_hash="sha256:0000",
        generation=1,
        contract_id="c1",
        patch_summary="Loop unroll",
        scope_res={"allowed": True},
        ast_res={"allowed": True},
        eval_res={"correctness_status": "PASS", "retained": True, "candidate_median_ms": 1.20},
        receipt={"receipt_id": "r1"}
    )
    # Cand 2: 0.80 ms (dominates Cand 1)
    db.record_candidate(
        candidate_hash="sha256:cand2",
        parent_candidate_hash="sha256:cand1",
        generation=2,
        contract_id="c1",
        patch_summary="AVX2 vectorization",
        scope_res={"allowed": True},
        ast_res={"allowed": True},
        eval_res={"correctness_status": "PASS", "retained": True, "candidate_median_ms": 0.80},
        receipt={"receipt_id": "r2"}
    )
    frontier = db.get_pareto_candidates()
    assert len(frontier) == 1
    assert frontier[0].candidate_hash == "sha256:cand2"


def test_negative_result_recorded_with_failure_category(temp_db_dir):
    db = ProgramDatabase(db_dir=temp_db_dir)
    rec = db.record_candidate(
        candidate_hash="sha256:cand_buggy",
        parent_candidate_hash="sha256:cand1",
        generation=2,
        contract_id="c1",
        patch_summary="Broke correctness",
        scope_res={"allowed": True},
        ast_res={"allowed": True},
        eval_res={
            "correctness_status": "FAIL",
            "retained": False,
            "message": "IndexError at line 42"
        },
        receipt={"receipt_id": "r3"}
    )
    assert not rec.retained_for_review
    assert rec.failure_category == "CORRECTNESS_FAILURE"
    assert "IndexError" in (rec.failure_message or "")
    assert len(db.get_negative_results()) == 1


def test_lineage_trace(temp_db_dir):
    db = ProgramDatabase(db_dir=temp_db_dir)
    db.record_candidate(
        candidate_hash="sha256:gen1",
        parent_candidate_hash="sha256:0000000000000000000000000000000000000000000000000000000000000000",
        generation=1,
        contract_id="c1",
        patch_summary="p1",
        scope_res={"allowed": True},
        ast_res={"allowed": True},
        eval_res={"correctness_status": "PASS", "retained": True, "candidate_median_ms": 1.5},
        receipt={}
    )
    db.record_candidate(
        candidate_hash="sha256:gen2",
        parent_candidate_hash="sha256:gen1",
        generation=2,
        contract_id="c1",
        patch_summary="p2",
        scope_res={"allowed": True},
        ast_res={"allowed": True},
        eval_res={"correctness_status": "PASS", "retained": True, "candidate_median_ms": 1.2},
        receipt={}
    )
    lineage = db.get_lineage("sha256:gen2")
    assert len(lineage) == 2
    assert lineage[0].candidate_hash == "sha256:gen2"
    assert lineage[1].candidate_hash == "sha256:gen1"


def test_persistence_roundtrip(temp_db_dir):
    db1 = ProgramDatabase(db_dir=temp_db_dir)
    db1.record_candidate(
        candidate_hash="sha256:cand_good",
        parent_candidate_hash="sha256:0000000000000000000000000000000000000000000000000000000000000000",
        generation=1,
        contract_id="c1",
        patch_summary="good",
        scope_res={"allowed": True},
        ast_res={"allowed": True},
        eval_res={"correctness_status": "PASS", "retained": True, "candidate_median_ms": 1.0},
        receipt={}
    )
    db1.record_candidate(
        candidate_hash="sha256:cand_bad",
        parent_candidate_hash="sha256:cand_good",
        generation=2,
        contract_id="c1",
        patch_summary="bad",
        scope_res={"allowed": True},
        ast_res={"allowed": True},
        eval_res={"correctness_status": "FAIL", "retained": False, "message": "Failed"},
        receipt={}
    )

    # Re-instantiate from same directory
    db2 = ProgramDatabase(db_dir=temp_db_dir)
    assert len(db2.candidates) == 2
    assert len(db2.get_pareto_candidates()) == 1
    assert len(db2.get_negative_results()) == 1
    assert db2.get_negative_results()[0].candidate_hash == "sha256:cand_bad"
