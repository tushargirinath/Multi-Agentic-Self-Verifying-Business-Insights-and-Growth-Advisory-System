"""Unit tests for Phase 5: Analyst Agent, Critic Agent & Orchestrator."""
import pytest
import duckdb
from app.data.bronze import BronzeManager
from app.data.silver import SilverManager
from app.data.gold import GoldManager
from app.agents.analyst import AnalystAgent
from app.agents.critic import CriticAgent
from app.orchestrator.graph import Orchestrator


@pytest.fixture(scope="module")
def prepared_db():
    con = duckdb.connect(":memory:")
    bronze = BronzeManager(con)
    bronze.load_raw_csv_to_bronze("data/raw/sales_transactions.csv", "ds_p5")
    silver = SilverManager(con)
    silver.apply_cleaning_plan("ds_p5")
    gold = GoldManager(con)
    gold.build_gold_marts("ds_p5")
    return con


def test_analyst_agent(prepared_db):
    analyst = AnalystAgent(prepared_db)
    answer = analyst.answer_question("What is total gross revenue?", dataset_id="ds_p5")

    assert "gross_revenue" in answer["numbers"]
    assert answer["numbers"]["gross_revenue"] > 60000000.0  # £62M+
    assert "currency=GBP" in answer["assumptions"]
    assert len(answer["queries"]) > 0
    assert answer["chart"]["type"] == "bar"


def test_critic_agent_verification_pass(prepared_db):
    analyst = AnalystAgent(prepared_db)
    critic = CriticAgent(prepared_db)

    answer = analyst.answer_question("What is total gross revenue?", dataset_id="ds_p5")
    verification = critic.verify_answer("What is total gross revenue?", answer, dataset_id="ds_p5")

    assert verification["verdict"] in ["pass", "pass_with_note"]
    assert verification["confidence"]["score"] >= 0.85
    assert verification["confidence"]["label"] == "High"
    assert verification["layers"]["L1_recompute"] == "pass"
    assert verification["layers"]["L2_sanity"] == "pass"


def test_critic_interception_on_corrupted_answer(prepared_db):
    critic = CriticAgent(prepared_db)

    # Deliberately corrupt the headline number (inflate by 20%)
    corrupted_answer = {
        "headline": "Total gross revenue is £85,000,000 across 25,000 orders.",
        "explanation": "Revenue surged significantly.",
        "numbers": {"gross_revenue": 85000000.0, "orders": 25000},
        "evidence": {"gross_revenue": 85000000.0},
        "assumptions": ["currency=GBP"]
    }

    verification = critic.verify_answer("What is total gross revenue?", corrupted_answer, dataset_id="ds_p5")
    # Critic must catch the corruption
    assert verification["verdict"] in ["repair", "block"]
    assert verification["layers"]["L1_recompute"] == "fail"
    assert len(verification["issues"]) > 0
    assert any(i["layer"] == "L1" for i in verification["issues"])


def test_orchestrator_execution(prepared_db):
    orch = Orchestrator(prepared_db)
    trace_events = []

    def on_event(ev):
        trace_events.append(ev["event"])

    state = orch.execute_question("What was net revenue by month?", dataset_id="ds_p5", event_callback=on_event)

    assert state.status == "completed"
    assert state.answer is not None
    assert state.verification["verdict"] in ["pass", "pass_with_note"]
    assert "run.started" in trace_events
    assert "verify.layer" in trace_events
    assert "run.completed" in trace_events
    assert state.spent.steps >= 2
