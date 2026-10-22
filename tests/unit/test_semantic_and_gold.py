"""Unit tests for Phase 3: Semantic Layer, Gold Marts & Lakehouse."""
import pytest
import duckdb
from app.data.bronze import BronzeManager
from app.data.silver import SilverManager
from app.data.gold import GoldManager
from app.semantic.compiler import SemanticCompiler
from app.data.db import AppDatabase


@pytest.fixture(scope="module")
def prepared_db():
    con = duckdb.connect(":memory:")
    bronze = BronzeManager(con)
    bronze.load_raw_csv_to_bronze("data/raw/sales_transactions.csv", "ds_p3")
    silver = SilverManager(con)
    silver.apply_cleaning_plan("ds_p3")
    gold = GoldManager(con)
    gold.build_gold_marts("ds_p3")
    return con


def test_semantic_compiler():
    compiler = SemanticCompiler()
    metrics = compiler.get_registered_metrics()
    assert "gross_revenue" in metrics
    assert "orders" in metrics
    assert "aov" in metrics
    assert "repeat_rate" in metrics

    # Compile metric with dimensions
    compiled = compiler.compile("gross_revenue", dimensions=["month"], dataset_id="ds_p3")
    assert "date_trunc('month', order_date)" in compiled["sql"]
    assert "fact_order_lines" in compiled["sql"]
    assert "GROUP BY 1" in compiled["sql"]


def test_gold_marts_materialization(prepared_db):
    # Verify gold_daily
    daily_count = prepared_db.execute("SELECT COUNT(*) FROM gold_daily WHERE dataset_id = 'ds_p3'").fetchone()[0]
    assert daily_count > 300  # ~1 year of days

    # Verify mart_customer_rfm
    rfm_count = prepared_db.execute("SELECT COUNT(*) FROM mart_customer_rfm WHERE dataset_id = 'ds_p3'").fetchone()[0]
    assert rfm_count > 4000

    segments = prepared_db.execute("""
        SELECT segment, COUNT(*) FROM mart_customer_rfm 
        WHERE dataset_id = 'ds_p3' GROUP BY 1
    """).fetchall()
    seg_dict = dict(segments)
    assert "Champions" in seg_dict
    assert "Loyal" in seg_dict
    assert "At Risk" in seg_dict

    # Verify basket pairs
    baskets = prepared_db.execute("SELECT COUNT(*) FROM mart_basket_pairs WHERE dataset_id = 'ds_p3'").fetchone()[0]
    assert baskets > 0

    top_pair = prepared_db.execute("""
        SELECT a_name, b_name, lift FROM mart_basket_pairs 
        WHERE dataset_id = 'ds_p3' ORDER BY lift DESC LIMIT 1
    """).fetchone()
    assert top_pair is not None
    assert top_pair[2] > 1.0  # Lift greater than 1 means positive correlation


def test_app_database(tmp_path):
    db_file = tmp_path / "test_app.db"
    db = AppDatabase(str(db_file))
    db.record_run({
        "id": "run_test_123",
        "dataset_id": "ds_p3",
        "user_id": "u_test",
        "intent": "describe",
        "question": "What is total revenue?",
        "status": "completed",
        "answer": {"headline": "Gross revenue is £62M."},
        "verification": {"status": "pass"},
        "tokens_in": 100,
        "tokens_out": 50,
        "seconds": 1.2
    })

    retrieved = db.get_run("run_test_123")
    assert retrieved is not None
    assert retrieved["id"] == "run_test_123"
    assert retrieved["answer"]["headline"] == "Gross revenue is £62M."
