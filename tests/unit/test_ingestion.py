"""Unit tests for Phase 1: Bronze Data Layer & Ingestion Agent."""
import os
import time
import pytest
import duckdb
from app.data.bronze import BronzeManager
from app.agents.ingestion import IngestionAgent
from app.config import settings


@pytest.fixture
def in_memory_con():
    con = duckdb.connect(":memory:")
    return con


def test_bronze_file_hash(tmp_path):
    sample_file = tmp_path / "sample.csv"
    sample_file.write_text("a,b,c\n1,2,3\n", encoding="utf-8")

    file_hash = BronzeManager.compute_file_hash(str(sample_file))
    assert isinstance(file_hash, str)
    assert len(file_hash) == 64  # SHA-256


def test_schema_mapping():
    agent = IngestionAgent(duckdb.connect(":memory:"))
    raw_headers = ["TransactionNo", "Date", "ProductNo", "ProductName", "Price", "Quantity", "CustomerNo", "Country"]
    result = agent.map_columns(raw_headers)

    mapping = result["mapping"]
    assert mapping["order_id"] == "TransactionNo"
    assert mapping["order_date"] == "Date"
    assert mapping["sku"] == "ProductNo"
    assert mapping["product_name"] == "ProductName"
    assert mapping["unit_price"] == "Price"
    assert mapping["quantity"] == "Quantity"
    assert mapping["customer_id"] == "CustomerNo"
    assert mapping["country"] == "Country"
    assert result["all_mapped"] is True
    assert result["confidence_scores"]["order_id"] >= 0.9


def test_capability_matrix():
    agent = IngestionAgent(duckdb.connect(":memory:"))
    mapping = {
        "order_id": "TransactionNo",
        "order_date": "Date",
        "sku": "ProductNo",
        "product_name": "ProductName",
        "unit_price": "Price",
        "quantity": "Quantity",
        "customer_id": "CustomerNo",
        "country": "Country",
    }
    caps = agent.evaluate_capabilities(mapping)
    cap_dict = {c["feature"]: c["status"] for c in caps}

    assert "Available" in cap_dict["Revenue, orders, units, AOV trends"]
    assert "Available" in cap_dict["Country analysis"]
    assert "Not available" in cap_dict["Profit and margin"]
    assert "Not available" in cap_dict["Stock-out prediction"]


@pytest.mark.skipif(not os.path.exists("data/raw/sales_transactions.csv"), reason="Reference dataset not found")
def test_full_dataset_profiling_performance(in_memory_con):
    agent = IngestionAgent(in_memory_con)
    csv_path = "data/raw/sales_transactions.csv"

    t0 = time.time()
    profile_result = agent.profile_dataset(csv_path, dataset_id="test_ds")
    elapsed = time.time() - t0

    print(f"\nProfiling completed in {elapsed:.2f} seconds.")
    # Requirement: Profiling under 30 seconds
    assert elapsed < 30.0

    profile = profile_result["profile"]
    assert profile["total_rows"] > 500000
    assert profile["unique_orders"] > 20000
    assert profile["unique_products"] > 3000
    assert profile["neg_quantities"] > 0
    assert profile_result["date_format_analysis"]["inferred_format"] == "%m/%d/%Y"
