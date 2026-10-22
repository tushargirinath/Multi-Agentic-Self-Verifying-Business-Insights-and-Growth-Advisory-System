"""Unit tests for Phase 2: Cleaning Rule Catalog, Quarantine & Data Quality Score."""
import pytest
import duckdb
from app.data.bronze import BronzeManager
from app.data.silver import SilverManager
from app.data.quality import DataQualityEngine
from app.data.rules.catalog import CLEANING_CATALOG


@pytest.fixture(scope="module")
def shared_db():
    con = duckdb.connect(":memory:")
    # Initialize bronze and load raw reference dataset
    bronze = BronzeManager(con)
    bronze.load_raw_csv_to_bronze("data/raw/sales_transactions.csv", dataset_id="ds_test")
    return con


def test_rule_catalog_structure():
    assert "CL-01" in CLEANING_CATALOG
    assert "CL-03" in CLEANING_CATALOG
    assert "CL-04" in CLEANING_CATALOG
    assert CLEANING_CATALOG["CL-03"].risk == "medium"
    assert CLEANING_CATALOG["CL-04"].mode == "auto"


def test_silver_cleaning_and_quarantine(shared_db):
    silver_mgr = SilverManager(shared_db)
    plan = silver_mgr.propose_cleaning_plan("ds_test")
    assert len(plan) >= 5

    res = silver_mgr.apply_cleaning_plan("ds_test")
    assert res["status"] == "applied"
    assert res["quarantined_row_count"] == 5587  # exact duplicate count verified earlier
    assert res["silver_row_count"] == 536350 - 5587

    # Verify quarantine records exist
    q_count = shared_db.execute("SELECT COUNT(*) FROM silver_quarantine WHERE dataset_id = 'ds_test'").fetchone()[0]
    assert q_count == 5587

    # Verify fact_order_lines view works
    fact_count = shared_db.execute("SELECT COUNT(*) FROM fact_order_lines WHERE dataset_id = 'ds_test'").fetchone()[0]
    assert fact_count == res["silver_row_count"]


def test_data_quality_score_and_distortion(shared_db):
    dq_engine = DataQualityEngine(shared_db)

    # Score before cleaning
    raw_dqs = dq_engine.calculate_dqs("ds_test", is_cleaned=False)
    assert raw_dqs["dqs"] >= 80.0
    assert raw_dqs["grade"] in ["Good", "Excellent"]

    # Score after cleaning
    clean_dqs = dq_engine.calculate_dqs("ds_test", is_cleaned=True)
    assert clean_dqs["dqs"] >= 90.0
    assert clean_dqs["grade"] == "Excellent"
    assert clean_dqs["dimensions"]["uniqueness"] == 1.0

    # Distortion estimator
    distortion = dq_engine.compute_distortion_estimator("ds_test")
    deltas = distortion["kpi_deltas"]

    assert deltas["gross_revenue"]["clean"] > 0
    assert deltas["gross_revenue"]["raw"] > deltas["gross_revenue"]["clean"]
    assert deltas["orders"]["clean"] > 0
    assert deltas["aov"]["clean"] > 0
    assert deltas["net_revenue"]["cancellation_rate_pct"] > 0
