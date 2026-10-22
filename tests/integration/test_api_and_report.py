"""Integration tests for Phase 7: Report Agent & FastAPI Gateway."""
import os
import time
import pytest
from starlette.testclient import TestClient
from app.api.main import app
from app.agents.report import ReportAgent
from app.data.bronze import BronzeManager
from app.data.silver import SilverManager
from app.data.gold import GoldManager
import duckdb


@pytest.fixture(scope="module")
def setup_api_data():
    # Ensure dataset is loaded into DuckDB
    from app.config import settings
    con = duckdb.connect(settings.duckdb_path)
    BronzeManager(con).load_raw_csv_to_bronze("data/raw/sales_transactions.csv", "ds_reference")
    SilverManager(con).apply_cleaning_plan("ds_reference")
    GoldManager(con).build_gold_marts("ds_reference")
    con.close()


def test_report_agent_generation(setup_api_data, tmp_path):
    report_agent = ReportAgent()
    t0 = time.time()
    rep_data = report_agent.generate_report_data("ds_reference")
    html_path = report_agent.render_html_report(rep_data, str(tmp_path / "test_report.html"))
    pdf_path = report_agent.render_pdf_report(rep_data, str(tmp_path / "test_report.pdf"))
    elapsed = time.time() - t0

    assert os.path.exists(html_path)
    assert os.path.exists(pdf_path)
    assert os.path.getsize(pdf_path) > 1000
    assert elapsed < 60.0  # Section 25.1 SLO: Report generation under 60s


def test_api_endpoints(setup_api_data):
    client = TestClient(app)

    # 1. Health check & Web UI
    res = client.get("/")
    assert res.status_code == 200
    assert "MAVIS" in res.text

    h_res = client.get("/health")
    assert h_res.status_code == 200
    assert h_res.json()["system"] == "MAVIS"

    # 2. Dataset profile
    p_res = client.get("/v1/datasets/ds_reference/profile")
    assert p_res.status_code == 200
    assert p_res.json()["profile"]["total_rows"] > 500000

    # 3. Quality score
    q_res = client.get("/v1/datasets/ds_reference/quality")
    assert q_res.status_code == 200
    assert q_res.json()["dqs_after"]["dqs"] >= 90.0

    # 4. Chat endpoint
    c_res = client.post("/v1/chat", json={"dataset_id": "ds_reference", "question": "What is total revenue?"})
    assert c_res.status_code == 202
    chat_body = c_res.json()
    assert chat_body["status"] == "completed"
    assert "gross_revenue" in chat_body["answer"]["numbers"]
    assert chat_body["verification"]["verdict"] in ["pass", "pass_with_note"]

    # 5. Recommendations
    r_res = client.get("/v1/recommendations?dataset_id=ds_reference")
    assert r_res.status_code == 200
    assert len(r_res.json()["recommendations"]) > 0

    # 6. Audit log & chain integrity
    a_res = client.get("/v1/audit")
    assert a_res.status_code == 200
    assert a_res.json()["chain_verification"]["valid"] is True

    # 7. Reports generation
    rep_res = client.post("/v1/reports", json={"dataset_id": "ds_reference", "format": "html"})
    assert rep_res.status_code == 200
    assert "report_id" in rep_res.json()
