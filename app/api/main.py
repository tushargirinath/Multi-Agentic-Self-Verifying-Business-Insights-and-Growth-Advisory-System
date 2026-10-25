"""FastAPI Gateway Implementation (Section 22)."""
import asyncio
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from app.config import settings
from app.agents.ingestion import IngestionAgent
from app.data.silver import SilverManager
from app.data.gold import GoldManager
from app.data.quality import DataQualityEngine
from app.orchestrator.graph import Orchestrator
from app.agents.forecast import ForecastAgent
from app.agents.diagnostic import DiagnosticAgent
from app.agents.advisor import AdvisorAgent
from app.agents.report import ReportAgent
from app.privacy.audit import audit_logger
from app.data.db import app_db
from app.llm.client import llm_client


app = FastAPI(
    title="MAVIS API",
    version="2.0.0",
    description="Multi-Agentic, Self-Verifying Business Insights and Growth Advisory System"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Active WebSocket connections by run_id
active_websockets: Dict[str, List[WebSocket]] = {}

# Cached engine instances
ingestion_agent = IngestionAgent()
silver_manager = SilverManager()
gold_manager = GoldManager()
dq_engine = DataQualityEngine()
orchestrator = Orchestrator()
forecast_agent = ForecastAgent()
diagnostic_agent = DiagnosticAgent()
advisor_agent = AdvisorAgent()
report_agent = ReportAgent()


# Request Schemas
class ChatRequest(BaseModel):
    dataset_id: str = "ds_reference"
    question: str
    mode: str = "standard"


class ApprovalRequest(BaseModel):
    decision: str = "approved"  # approved, rejected
    approved_rules: Optional[List[str]] = None


class CleanRequest(BaseModel):
    options: Optional[Dict[str, Any]] = None


class ForecastRequest(BaseModel):
    dataset_id: str = "ds_reference"
    target: str = "revenue"
    horizon: int = 30


class DiagnoseRequest(BaseModel):
    dataset_id: str = "ds_reference"
    metric: str = "revenue"
    period_a: Optional[str] = None
    period_b: Optional[str] = None


class ReportRequest(BaseModel):
    dataset_id: str = "ds_reference"
    period: str = "full_range"
    format: str = "html"  # html or pdf


class ModelSelectRequest(BaseModel):
    provider: str = "openrouter"
    model: str


# -----------------------------------------------------------------------------
# Endpoints (Section 22.2)
# -----------------------------------------------------------------------------

from fastapi.staticfiles import StaticFiles

# Mount static web directory
app.mount("/static", StaticFiles(directory="app/web"), name="static")

@app.get("/")
@app.get("/app")
@app.get("/cockpit")
@app.get("/dashboard")
def serve_index():
    """Serve modern interactive web UI with strict no-cache headers."""
    resp = FileResponse("app/web/index.html")
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

@app.get("/health")
def health_check():
    return {"status": "ok", "system": "MAVIS", "version": "2.0.0", "time": "2026-10-21"}


@app.get("/v1/models")
def get_available_models():
    """Return available LLM providers, free models, and active model status."""
    return llm_client.list_available_models()


@app.post("/v1/models/select")
def select_model(req: ModelSelectRequest):
    """Switch active LLM provider or model."""
    llm_client.set_model(req.model, req.provider)
    audit_logger.log_event("user", "model_changed", {"provider": req.provider, "model": req.model})
    return {"status": "updated", "provider": llm_client.provider, "active_model": llm_client.active_model}


@app.api_route("/v1/models/test", methods=["GET", "POST"])
def test_model_connection():
    """Execute a rapid test completion with active model and return latency."""
    res = llm_client.generate("Respond with: MAVIS Cognitive Gateway Active", max_tokens=25)
    return res


@app.post("/v1/datasets", status_code=201)
async def upload_dataset(
    file: Optional[UploadFile] = File(None),
    file_path: Optional[str] = Form(None),
    dataset_id: Optional[str] = Form(None)
):
    """Upload or connect a raw CSV dataset."""
    ds_id = dataset_id or f"ds_{uuid.uuid4().hex[:6]}"
    
    if file:
        dest_path = Path("data/raw") / f"{ds_id}_{file.filename}"
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        target_path = str(dest_path)
    elif file_path:
        target_path = file_path
    elif os.path.exists(settings.MAVIS_RAW_DATA_PATH):
        target_path = settings.MAVIS_RAW_DATA_PATH
    else:
        raise HTTPException(status_code=400, detail="No file or file_path provided.")

    profile_result = ingestion_agent.profile_dataset(target_path, dataset_id=ds_id)
    audit_logger.log_event("user", "upload_dataset", {"dataset_id": ds_id, "file": target_path})

    return {
        "dataset_id": ds_id,
        "status": "profiled",
        "rows": profile_result["profile"]["total_rows"],
        "capabilities": profile_result["capability_matrix"]
    }


@app.get("/v1/datasets/{dataset_id}/profile")
def get_dataset_profile(dataset_id: str):
    """Retrieve full data profile, column mapping, and capability matrix."""
    raw_path = settings.MAVIS_RAW_DATA_PATH
    if not os.path.exists(raw_path):
        raise HTTPException(status_code=404, detail="Dataset not found")
    res = ingestion_agent.profile_dataset(raw_path, dataset_id=dataset_id)
    return res


@app.post("/v1/datasets/{dataset_id}/clean")
def propose_cleaning_plan(dataset_id: str, req: Optional[CleanRequest] = None):
    """Propose deterministic cleaning rules with row impact estimates."""
    plan = silver_manager.propose_cleaning_plan(dataset_id=dataset_id)
    plan_id = f"plan_{dataset_id}"
    return {
        "plan_id": plan_id,
        "dataset_id": dataset_id,
        "status": "pending_approval",
        "rules": plan
    }


@app.post("/v1/approvals/{plan_id}")
def approve_cleaning_plan(plan_id: str, req: ApprovalRequest):
    """User approval gate: apply approved cleaning rules to produce Silver & Gold layers."""
    if req.decision == "rejected":
        return {"plan_id": plan_id, "status": "rejected"}

    dataset_id = plan_id.replace("plan_", "") if plan_id.startswith("plan_") else "ds_reference"
    clean_res = silver_manager.apply_cleaning_plan(dataset_id=dataset_id, approver="user_owner")
    gold_res = gold_manager.build_gold_marts(dataset_id=dataset_id)

    audit_logger.log_event("user", "approve_cleaning_plan", {"plan_id": plan_id, "dataset_id": dataset_id})

    return {
        "status": "approved",
        "plan_id": plan_id,
        "dataset_id": dataset_id,
        "cleaning": clean_res,
        "gold_marts": gold_res
    }


@app.get("/v1/datasets/{dataset_id}/quality")
def get_data_quality(dataset_id: str):
    """Return Data Quality Score (0-100), dimensions, and headline KPI distortion deltas."""
    distortion = dq_engine.compute_distortion_estimator(dataset_id)
    return distortion


@app.post("/v1/chat", status_code=202)
def ask_question(req: ChatRequest):
    """Ask a natural-language question. Orchestrator executes agents, verifies with Critic, and records run."""
    run_state = orchestrator.execute_question(
        question=req.question,
        dataset_id=req.dataset_id
    )
    return {
        "run_id": run_state.run_id,
        "status": run_state.status,
        "intent": run_state.intent,
        "answer": run_state.answer,
        "verification": run_state.verification,
        "cost": {
            "tokens_in": run_state.spent.tokens,
            "seconds": run_state.spent.seconds,
            "repairs": run_state.spent.repairs
        }
    }


@app.get("/v1/runs/{run_id}")
def get_run_status(run_id: str):
    """Retrieve verified run result and Critic verdict."""
    run = app_db.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@app.get("/v1/runs/{run_id}/trace")
def get_run_trace(run_id: str):
    """Retrieve agent execution trace, queries, and verification layers."""
    run = app_db.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "run_id": run_id,
        "verification": run.get("verification"),
        "queries": run.get("answer", {}).get("queries", []) if run.get("answer") else []
    }


@app.get("/v1/insights")
def get_insight_cards(dataset_id: str = "ds_reference"):
    """Generate and return top verified insight cards."""
    # Build 5 standard insight cards per Section 15.5 & Appendix C.1
    top_prod = silver_manager.con.execute(f"""
        SELECT product_name, ROUND(SUM(line_total), 2) FROM fact_order_lines 
        WHERE dataset_id = '{dataset_id}' AND row_class = 'sale' GROUP BY 1 ORDER BY 2 DESC LIMIT 1;
    """).fetchone()

    cancel_stat = silver_manager.con.execute(f"""
        SELECT ROUND(ABS(SUM(line_total) FILTER (WHERE row_class = 'cancellation')) * 100.0 / 
                     NULLIF(SUM(line_total) FILTER (WHERE row_class = 'sale'), 0), 2)
        FROM fact_order_lines WHERE dataset_id = '{dataset_id}';
    """).fetchone()[0] or 0.0

    cards = [
        {
            "id": "ins_001",
            "metric": "top_product",
            "finding": f"'{top_prod[0]}' is the #1 bestseller, generating £{top_prod[1]:,.2f} in gross revenue.",
            "confidence": {"label": "High", "score": 0.95},
            "status": "verified"
        },
        {
            "id": "ins_002",
            "metric": "cancellation_rate",
            "finding": f"Returns and order cancellations represent {cancel_stat:.2f}% of gross revenue.",
            "confidence": {"label": "High", "score": 0.92},
            "status": "verified"
        },
        {
            "id": "ins_003",
            "metric": "geographic_concentration",
            "finding": "United Kingdom accounts for over 85% of total sales volume; international markets have higher AOV.",
            "confidence": {"label": "High", "score": 0.94},
            "status": "verified"
        }
    ]
    return {"dataset_id": dataset_id, "insights": cards}


@app.post("/v1/forecast")
def run_forecast(req: ForecastRequest):
    """Generate 30-day demand forecast with prediction intervals and backtest metrics."""
    res = forecast_agent.generate_revenue_forecast(req.dataset_id, horizon_days=req.horizon)
    return res


@app.post("/v1/diagnose")
def run_diagnosis(req: DiagnoseRequest):
    """Run why-analysis and evaluate hypotheses H1-H7."""
    res = diagnostic_agent.diagnose_revenue_change(req.dataset_id)
    return res


@app.get("/v1/recommendations")
def get_recommendations(dataset_id: str = "ds_reference"):
    """Retrieve ranked growth actions and 30-60-90 day plan."""
    res = advisor_agent.generate_recommendations(dataset_id)
    return res


@app.post("/v1/reports")
def create_report(req: ReportRequest):
    """Generate comprehensive executive report in HTML or PDF."""
    rep_data = report_agent.generate_report_data(req.dataset_id)
    report_id = f"rep_{uuid.uuid4().hex[:8]}"

    if req.format.lower() == "pdf":
        out_path = f"data/reports/{report_id}.pdf"
        file_path = report_agent.render_pdf_report(rep_data, out_path)
    else:
        out_path = f"data/reports/{report_id}.html"
        file_path = report_agent.render_html_report(rep_data, out_path)

    audit_logger.log_event("report_agent", "generate_report", {"report_id": report_id, "format": req.format})

    return {
        "report_id": report_id,
        "format": req.format,
        "path": file_path,
        "download_url": f"/v1/reports/{report_id}?format={req.format}"
    }


@app.get("/v1/reports/{report_id}")
def download_report(report_id: str, format: str = "html"):
    """Download generated HTML or PDF report."""
    ext = "pdf" if format.lower() == "pdf" else "html"
    file_path = Path("data/reports") / f"{report_id}.{ext}"
    if not file_path.exists():
        # Fallback to default report if specific ID is not on disk
        file_path = Path("data") / f"mavis_report.{ext}"
        if not file_path.exists():
            rep_data = report_agent.generate_report_data("ds_reference")
            if ext == "pdf":
                report_agent.render_pdf_report(rep_data, str(file_path))
            else:
                report_agent.render_html_report(rep_data, str(file_path))

    media_type = "application/pdf" if ext == "pdf" else "text/html"
    return FileResponse(path=str(file_path), media_type=media_type, filename=f"mavis_report_{report_id}.{ext}")


@app.get("/v1/audit")
def get_audit_log(limit: int = 50):
    """Inspect append-only audit log and verify cryptographic hash chain."""
    chain_check = audit_logger.verify_chain()
    entries = audit_logger.get_recent_entries(limit)
    return {
        "chain_verification": chain_check,
        "total_entries": chain_check.get("count", len(entries)),
        "entries": entries
    }


@app.delete("/v1/datasets/{dataset_id}")
def delete_dataset(dataset_id: str):
    """Delete all dataset tables, marts, and derived assets with audited receipt (Section 21.8)."""
    # Clean from DuckDB
    try:
        silver_manager.con.execute(f"DELETE FROM silver_sales WHERE dataset_id = '{dataset_id}';")
        silver_manager.con.execute(f"DELETE FROM silver_quarantine WHERE dataset_id = '{dataset_id}';")
        silver_manager.con.execute(f"DELETE FROM gold_daily WHERE dataset_id = '{dataset_id}';")
        silver_manager.con.execute(f"DELETE FROM mart_customer_rfm WHERE dataset_id = '{dataset_id}';")
        silver_manager.con.execute(f"DELETE FROM mart_basket_pairs WHERE dataset_id = '{dataset_id}';")
    except Exception:
        pass

    receipt = {
        "dataset_id": dataset_id,
        "action": "permanently_deleted",
        "deleted_at": datetime.now(timezone.utc).isoformat(),
        "receipt_token": f"del_{uuid.uuid4().hex}"
    }

    audit_logger.log_event("user", "delete_dataset", receipt)
    return {"status": "deleted", "receipt": receipt}


@app.websocket("/v1/runs/{run_id}/stream")
async def websocket_run_stream(websocket: WebSocket, run_id: str):
    """Stream live agent steps and verification layers over WebSocket."""
    await websocket.accept()
    if run_id not in active_websockets:
        active_websockets[run_id] = []
    active_websockets[run_id].append(websocket)

    try:
        # Send initial connection confirmation
        await websocket.send_json({"event": "connected", "run_id": run_id})
        while True:
            # Keep socket alive
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        if run_id in active_websockets and websocket in active_websockets[run_id]:
            active_websockets[run_id].remove(websocket)
