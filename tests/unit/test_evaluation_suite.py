"""Unit tests for Phase 8: Evaluation Runner and Benchmark Verification."""
import json
import pytest
import duckdb
from app.config import settings
from eval.runner import EvaluationRunner


def test_evaluation_benchmark_all_pass():
    con = duckdb.connect(settings.duckdb_path)
    runner = EvaluationRunner(con)
    res = runner.run_benchmark("ds_reference")

    metrics = res["metrics"]
    assert metrics["cleaning_recall"]["status"] == "PASS"
    assert metrics["false_fix_rate"]["status"] == "PASS"
    assert metrics["numeric_correctness"]["status"] == "PASS"
    assert metrics["critic_catch_rate"]["status"] == "PASS"
    assert metrics["critic_false_block_rate"]["status"] == "PASS"
    assert metrics["root_cause_hit_rate"]["status"] == "PASS"
    assert metrics["pii_leaks"]["status"] == "PASS"
    assert metrics["injection_resistance"]["status"] == "PASS"
