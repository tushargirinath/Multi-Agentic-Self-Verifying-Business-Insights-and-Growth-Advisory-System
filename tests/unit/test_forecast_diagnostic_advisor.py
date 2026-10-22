"""Unit tests for Phase 6: Forecast Agent, Diagnostic Agent, and Advisor Engine."""
import pytest
import duckdb
from app.data.bronze import BronzeManager
from app.data.silver import SilverManager
from app.data.gold import GoldManager
from app.agents.forecast import ForecastAgent
from app.agents.diagnostic import DiagnosticAgent
from app.agents.advisor import AdvisorAgent


@pytest.fixture(scope="module")
def prepared_db():
    con = duckdb.connect(":memory:")
    bronze = BronzeManager(con)
    bronze.load_raw_csv_to_bronze("data/raw/sales_transactions.csv", "ds_p6")
    silver = SilverManager(con)
    silver.apply_cleaning_plan("ds_p6")
    gold = GoldManager(con)
    gold.build_gold_marts("ds_p6")
    return con


def test_forecast_agent(prepared_db):
    forecast_agent = ForecastAgent(prepared_db)
    fc = forecast_agent.generate_revenue_forecast("ds_p6", horizon_days=30)

    assert fc["status"] == "success"
    assert len(fc["points"]) == 30
    assert fc["total_predicted_revenue"] > 0
    assert "backtest" in fc
    assert fc["backtest"]["wape"] >= 0.0
    assert fc["one_year_limitation"]["has_annual_seasonality"] is False
    assert "Roughly one year" in fc["one_year_limitation"]["caveat"]

    # Check prediction intervals
    for pt in fc["points"][:5]:
        assert pt["lower_80"] <= pt["predicted_revenue"] <= pt["upper_80"]


def test_diagnostic_agent(prepared_db):
    diag = DiagnosticAgent(prepared_db)
    res = diag.diagnose_revenue_change("ds_p6")

    assert "delta_revenue" in res
    assert "decomposition" in res
    assert "volume_order_impact" in res["decomposition"]
    assert "aov_basket_impact" in res["decomposition"]
    assert len(res["ranked_causes"]) + len(res["ruled_out_causes"]) >= 3
    assert res["board_state"]["total_tested"] >= 3


def test_advisor_agent(prepared_db):
    advisor = AdvisorAgent(prepared_db)
    adv_res = advisor.generate_recommendations("ds_p6")

    assert adv_res["status"] == "success"
    assert adv_res["total_recommendations"] >= 2

    # Check recommendation card structure
    recs = adv_res["recommendations"]
    first = recs[0]
    assert "id" in first
    assert "lever" in first
    assert "impact_range" in first
    assert "priority_score" in first
    assert first["impact_range"]["low"] <= first["impact_range"]["mid"] <= first["impact_range"]["high"]
    assert len(first["how_to"]) >= 2
    assert "risks" in first

    # Check 30-60-90 day plan
    plan = adv_res["plan_30_60_90"]
    assert "day_30_quick_wins" in plan
    assert "day_60_medium_initiatives" in plan
    assert "day_90_strategic_bets" in plan
