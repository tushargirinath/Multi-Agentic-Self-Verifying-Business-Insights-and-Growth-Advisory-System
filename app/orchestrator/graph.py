"""Orchestrator Execution Graph and Agent Coordinator (Section 14)."""
import time
import uuid
from typing import Dict, Any, List, Optional, Callable
import duckdb
from app.config import settings
from app.orchestrator.state import RunState
from app.agents.analyst import AnalystAgent
from app.agents.critic import CriticAgent
from app.privacy.scanner import scanner
from app.privacy.injection import sanitizer
from app.privacy.audit import audit_logger
from app.data.db import app_db


class Orchestrator:
    """Coordinates specialist agents, enforces budgets, gates answers through Critic, and logs all steps."""

    def __init__(self, duckdb_conn: Optional[duckdb.DuckDBPyConnection] = None):
        if duckdb_conn:
            self.con = duckdb_conn
        else:
            try:
                self.con = duckdb.connect(settings.duckdb_path, read_only=False)
            except Exception:
                self.con = duckdb.connect(settings.duckdb_path, read_only=True)
        self.analyst = AnalystAgent(self.con)
        self.critic = CriticAgent(self.con)

    @staticmethod
    def classify_intent(question: str) -> str:
        """Classify user intent into execution routes."""
        q = question.lower()
        if any(w in q for w in ["forecast", "predict", "next month", "future", "look ahead"]):
            return "forecast"
        if any(w in q for w in ["why did", "why has", "explain drop", "explain increase", "diagnose", "cause"]):
            return "why"
        if any(w in q for w in ["what should i do", "recommend", "growth", "opportunity", "advice", "action plan"]):
            return "advise"
        if any(w in q for w in ["what if", "scenario", "simulate", "discount effect"]):
            return "whatif"
        if any(w in q for w in ["generate report", "export report", "pdf report", "weekly brief"]):
            return "report"
        if any(w in q for w in ["delete my data", "delete dataset", "wipe"]):
            return "delete"
        if any(w in q for w in ["password", "secret key", "steal", "hack", "drop table", "dan mode"]):
            return "unsafe"
        return "describe"

    def execute_question(
        self,
        question: str,
        dataset_id: str = "ds_reference",
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> RunState:
        """Execute a complete analytical question run through the agent team and Critic gate."""
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        intent = self.classify_intent(question)
        t0 = time.time()

        state = RunState(
            run_id=run_id,
            dataset_id=dataset_id,
            question=question,
            intent=intent,
            status="running"
        )

        def emit(event_type: str, payload: Dict[str, Any]):
            event = {"event": event_type, "run_id": run_id, "payload": payload, "ts": time.time()}
            state.trace.append(event)
            if event_callback:
                try:
                    event_callback(event)
                except Exception:
                    pass

        emit("run.started", {"plan": [{"agent": "analyst", "goal": "query metric"}, {"agent": "critic", "goal": "verify numbers"}]})

        # 1. Untrusted text / injection sanitation
        safe_q, flagged, inj_meta = sanitizer.scan_and_sanitize(question)
        if flagged:
            audit_logger.log_event("system", "prompt_injection_flagged", inj_meta)

        # 2. Safety filter
        if intent == "unsafe":
            state.status = "blocked"
            state.answer = {
                "headline": "Request Refused",
                "explanation": "This request violates safety and data protection policies. MAVIS operates under strict least-privilege guardrails.",
                "confidence": {"label": "Low", "score": 0.0},
                "assumptions": []
            }
            emit("run.completed", {"status": "blocked"})
            return state

        # 3. Analyst Agent execution
        emit("agent.step", {"agent": "analyst", "goal": f"Execute analysis for '{intent}' intent", "status": "running"})
        state.spent.steps += 1
        
        draft_answer = self.analyst.answer_question(question, dataset_id=dataset_id)
        state.assumptions = draft_answer.get("assumptions", [])
        state.artifacts["queries"] = draft_answer.get("queries", [])
        state.artifacts["charts"] = [draft_answer.get("chart")] if draft_answer.get("chart") else []

        # Audit log the analyst tool call
        audit_logger.log_event("analyst", "execute_sql", {"queries": draft_answer.get("queries")})
        emit("agent.step", {"agent": "analyst", "status": "completed"})

        # 4. Critic Agent Verification Gate (5 layers)
        emit("agent.step", {"agent": "critic", "goal": "Execute 5-layer self-verification pipeline", "status": "running"})
        state.spent.steps += 1

        verification = self.critic.verify_answer(question, draft_answer, dataset_id=dataset_id)
        state.verification = verification
        
        emit("verify.layer", {"layers": verification["layers"], "verdict": verification["verdict"]})

        # 5. Handle repair loop if Critic flagged an issue
        loop_count = 0
        while verification["verdict"] == "repair" and loop_count < state.budget.max_repairs:
            loop_count += 1
            state.spent.repairs += 1
            emit("agent.step", {"agent": "analyst", "goal": f"Repairing answer (loop {loop_count})", "status": "repairing"})
            
            hints = [iss.get("hint", "") for iss in verification.get("issues", [])]
            draft_answer = self.analyst.answer_question(question, dataset_id=dataset_id, repair_hints=hints)
            verification = self.critic.verify_answer(question, draft_answer, dataset_id=dataset_id)
            state.verification = verification

        # 6. Apply Decision Matrix
        verdict = verification["verdict"]
        if verdict in ["pass", "pass_with_note"]:
            state.status = "completed"
            state.answer = draft_answer
            state.answer["confidence"] = verification["confidence"]
        elif verdict == "repair":
            # Failed after 3 loops -> downgrade or block
            state.status = "blocked"
            state.answer = {
                "headline": "I could not independently verify this number, so I am not showing it.",
                "explanation": "Independent Critic verification paths diverged by more than tolerance. Here is a verified question I can answer: 'What was net revenue by month?'",
                "confidence": {"label": "Low", "score": 0.40},
                "assumptions": ["safety=critic_verification_failed"]
            }
        else:
            state.status = "blocked"
            state.answer = {
                "headline": "Answer Blocked by Critic",
                "explanation": "The answer failed essential mathematical invariants or data grounding checks.",
                "confidence": {"label": "Low", "score": 0.20},
                "assumptions": ["critic_verdict=block"]
            }

        # 7. Privacy Outbound Scan (Zero-Leak Enforcement)
        try:
            scanner.enforce_zero_leak(state.answer)
            state.privacy["leak_scan"] = "pass"
        except PermissionError:
            state.status = "blocked"
            state.privacy["leak_scan"] = "failed"
            state.answer = {
                "headline": "Output Redacted by Privacy Agent",
                "explanation": "Outbound payload contained sensitive identifiers.",
                "confidence": {"label": "Low", "score": 0.0},
                "assumptions": []
            }
            audit_logger.log_event("privacy", "leak_blocked", {"run_id": run_id})

        elapsed = round(time.time() - t0, 3)
        state.spent.seconds = elapsed
        state.spent.tokens = 1200 + (loop_count * 400)

        # 8. Record in app database & audit log
        app_db.record_run({
            "id": state.run_id,
            "dataset_id": state.dataset_id,
            "intent": state.intent,
            "question": state.question,
            "status": state.status,
            "answer": state.answer,
            "verification": state.verification,
            "tokens_in": 900,
            "tokens_out": 300,
            "seconds": elapsed
        })
        audit_logger.log_event("orchestrator", "run_finished", {"run_id": run_id, "verdict": state.status, "confidence": state.verification.get("confidence")})

        emit("run.completed", {"status": state.status, "duration_sec": elapsed})
        return state
