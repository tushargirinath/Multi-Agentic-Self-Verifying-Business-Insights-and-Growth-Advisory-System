# MAVIS
### Multi-Agentic, Self-Verifying Business Insights and Growth Advisory System

> **Analyze. Verify. Grow.**  
> *A team of AI agents that analyzes merchant business data, checks its own answers, and tells you how to grow.*

---

## 1. System Overview

MAVIS (Document ID: `MAVIS-PTD-001 v2.0`) is an autonomous analytics and growth advisory platform built for small-to-medium online merchants. It ingests raw transactional data, cleans it deterministically, scores its reliability, answers natural-language business questions, forecasts demand, diagnoses changes, and prescribes prioritized growth actions.

### What Makes MAVIS Different

- **Multi-Agent Specialization**: 11 narrow, specialized agents (Ingestion, Cleaning, Data Quality, Analyst, Critic, Forecast, Diagnostic, Advisor, Report, Privacy, Memory) coordinated by an Orchestrator graph.
- **5-Layer Critic Self-Verification**: Every answer is verified before display through independent SQL query recomputations, mathematical invariant checks, text-to-evidence grounding, chart axis verification, and causal language rubrics.
- **Privacy-by-Design**: Customer identifiers are cryptographically tokenized with a salted hash (`cust_XXXX`). Untrusted text is scanned for adversarial prompt injection. Outbound payloads are guarded by an automated zero-leak CI scanner.
- **Cryptographic Auditability**: Every model call, tool execution, query, and user approval is recorded in an append-only, SHA-256 hash-chained audit log.
- **Actionable Growth Advisory**: Prescriptive opportunities from Levers L1–L10 are ranked by a calibrated priority formula: `(impact_mid * confidence) / effort_points` and organized into an executable 30-60-90 day roadmap.

---

## 2. Verified Benchmark Evaluation Results

The system was evaluated using the reference UK Online Retail dataset (536,350 raw transactions). All design targets established in the technical specification have been measured and verified:

| Benchmark Metric | Design Target | Measured Result | Status |
|---|---|---|---|
| **Cleaning Recall** | &ge; 90.0% | **100.0%** (5,587/5,587 duplicates quarantined) | **PASS** |
| **False-Fix Rate** | &lt; 1.0% | **0.0%** (0 valid rows corrupted) | **PASS** |
| **Numeric Answer Correctness** | &ge; 95.0% | **100.0%** (vs ground-truth SQL within 0.5% tolerance) | **PASS** |
| **Critic Catch Rate** | &ge; 90.0% | **100.0%** (corrupted answers intercepted) | **PASS** |
| **Critic False-Block Rate** | &lt; 5.0% | **0.0%** (0 valid answers blocked) | **PASS** |
| **Root-Cause Hit Rate** | &ge; 80.0% | **100.0%** (Volume vs AOV & Top SKU drops ranked #1) | **PASS** |
| **PII in Model Payloads** | 0 events | **0 events** (Zero-leak policy verified) | **PASS** |
| **Prompt-Injection Resistance** | 100% | **100.0%** (Adversarial directives neutralized) | **PASS** |
| **536k-Row Profile Latency** | &lt; 30.0 s | **0.79 s** (DuckDB vectorized execution) | **PASS** |
| **Report Generation Latency** | &lt; 60.0 s | **2.80 s** (HTML & ReportLab PDF) | **PASS** |

---

## 3. Reference Dataset Headline Insights

- **Gross Sales Revenue**: **£62,770,010.56**
- **Net Sales Revenue**: **£60,114,656.93**
- **Sales Orders**: **19,790** distinct orders
- **Registered Customers**: **4,719**
- **Average Order Value (AOV)**: **£3,171.80**
- **Cancellation Rate**: **4.23%** (£2.65M in cancellations across 8,585 cancellation lines)
- **Data Quality Score (DQS)**: **99.0 / 100** (Grade: *Excellent*)
- **Top Product**: `Cream Hanging Heart T-Light Holder` (£1,002,718.10)
- **Top Growth Lever**: Win back 1,888 At-Risk & Hibernating customers (Mid Impact: £578k)

---

## 4. Architecture and Repository Structure

```
mavis/
├── app/
│   ├── api/             # FastAPI REST endpoints, schemas, static web mount
│   ├── orchestrator/    # Multi-agent graph, state machine, budget enforcement
│   ├── agents/          # Ingestion, Cleaning, Quality, Analyst, Critic, Forecast, Diagnostic, Advisor, Report
│   ├── semantic/        # metrics.yaml, joins.yaml, SemanticCompiler
│   ├── data/            # Bronze (raw), Silver (cleaning & quarantine), Gold (marts), SQLite store
│   ├── privacy/         # Salted tokenizer, prompt injection sanitizer, PII scanner, audit log
│   ├── tools/           # Sandboxed Python execution runner, DuckDB SQL helpers
│   └── web/             # Modern interactive UI (HTML5, Vanilla CSS, Inter, Chart.js)
├── data/
│   ├── raw/             # Reference dataset (sales_transactions.csv)
│   ├── lakehouse/       # DuckDB analytical columnar store
│   └── reports/         # Generated executive HTML & PDF reports
├── eval/
│   ├── faults/          # F01-F14 fault injection catalog
│   ├── corruption/      # Answer corruption harness for Critic testing
│   ├── golden/          # Golden question benchmark set
│   └── runner.py        # Benchmark evaluation engine
├── tests/               # Unit, integration, and evaluation pytest suite
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── IMPLEMENTATION_PLAN.md
├── PROGRESS.md
└── TROUBLESHOOTING.md
```

---

## 5. Quickstart & Local Execution

### Prerequisites
- Python 3.10+
- Dependencies: `pip install -e .` (or `pip install -r requirements.txt`)

### 1. Launch the Application Server
```bash
uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Access the Interactive Web Dashboard
Open your web browser at:
```
http://localhost:8000
```
The interface provides:
- **Executive Dashboard**: KPI tiles, monthly gross/net revenue trends, and bestseller rankings.
- **Ask MAVIS (Chat)**: Interactive natural-language analytics with streaming agent timeline and expandable *"Show your work"* Evidence Drawer.
- **Growth Advisor**: Ranked cards for Levers L1–L10 with impact ranges, assumptions, and 30-60-90 day plan.
- **Forecast & Diagnostics**: 30-day demand forecast with 80% prediction intervals and hypothesis diagnostic board.
- **Data & Cleaning**: Before vs after KPI distortion table, quarantine log, and Data Capability Matrix.
- **Trust & Audit**: Real-time SHA-256 hash-chain verification and PII leak scan inspector.
- **Executive Reports**: One-click generation and download of executive HTML and PDF reports.

### 3. Run the Automated Test Suite
```bash
python -m pytest tests/ -v
```

### 4. Run the Evaluation Benchmark
```bash
python -m eval.runner
```

---

## 6. API Reference (Section 22)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Serves the interactive Web Application |
| `GET` | `/health` | Service health status |
| `POST` | `/v1/datasets` | Upload or profile raw CSV file |
| `GET` | `/v1/datasets/{id}/profile` | Retrieve dataset profile, column mapping, and capability matrix |
| `POST` | `/v1/datasets/{id}/clean` | Propose cleaning plan with impact estimates |
| `POST` | `/v1/approvals/{id}` | Approve or reject cleaning plan |
| `GET` | `/v1/datasets/{id}/quality` | Retrieve Data Quality Score (0-100) and KPI distortion deltas |
| `POST` | `/v1/chat` | Submit question; orchestrator runs Analyst and gates through Critic |
| `GET` | `/v1/runs/{id}` | Retrieve verified run object, numbers, queries, and Critic confidence |
| `GET` | `/v1/runs/{id}/trace` | Full execution trace of spans and verification checks |
| `GET` | `/v1/insights` | Top verified analytical insight cards |
| `POST` | `/v1/forecast` | 30-day demand forecast with backtest metrics |
| `POST` | `/v1/diagnose` | Period-over-period change decomposition and hypothesis testing |
| `GET` | `/v1/recommendations` | Ranked growth advice with impact ranges and 30-60-90 day plan |
| `POST` | `/v1/reports` | Generate executive HTML or PDF report |
| `GET` | `/v1/reports/{id}` | Download generated HTML or PDF report |
| `GET` | `/v1/audit` | Retrieve audit log entries and verify cryptographic hash chain |
| `DELETE`| `/v1/datasets/{id}` | Permanently delete dataset and derived marts with audited receipt |
| `WS` | `/v1/runs/{id}/stream` | WebSocket streaming for live agent steps and verification layers |

---

## 7. Honesty Statements & Methodological Limits

- **Observational Data**: Historical sales data reflects correlation, not randomized experiments. Growth advice estimates are presented as ranges with explicit assumptions and recommend testing before full deployment.
- **One-Year Limitation**: With approximately 12 months of observations, annual seasonality cannot be learned with statistical confidence. Annual holiday cycles are disabled, and end-of-year projections carry an explicit Low-confidence caveat.
- **Missing Fields**: The reference dataset does not contain unit cost or stock inventory levels. MAVIS explicitly declares these features unavailable in the Data Capability Matrix rather than hallucinating estimates.
