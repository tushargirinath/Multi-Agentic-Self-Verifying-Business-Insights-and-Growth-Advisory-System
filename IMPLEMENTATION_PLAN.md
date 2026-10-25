# MAVIS Implementation Plan
Multi-Agentic, Self-Verifying Business Insights and Growth Advisory System

Based on Product and Technical Documentation Document ID: MAVIS-PTD-001 v2.0.

---

## Phase Overview and Status

- [x] **Phase 1: Environment Setup, Project Layout & Ingestion Agent**
- [x] **Phase 2: Cleaning Rule Catalog, Quarantine & Data Quality Score (DQS)**
- [x] **Phase 3: Semantic Layer, Gold Data Marts & DuckDB Analytics Engine**
- [x] **Phase 4: Privacy Agent, Untrusted Text Sanitizer & Hash-Chained Audit Log**
- [x] **Phase 5: Analyst Agent, Critic Agent (Self-Verification Pipeline) & Orchestrator**
- [x] **Phase 6: Forecast Agent, Diagnostic Engine & Growth Advisory Levers**
- [x] **Phase 7: Report Agent (HTML/PDF) & FastAPI Gateway with WebSocket Streaming**
- [x] **Phase 8: Evaluation Harness, Planted Faults & Golden Questions Suite**
- [x] **Phase 9: Interactive Modern Web UI (Dashboard, Chat, Evidence Drawer, Trust View)**
- [x] **Phase 10: Full System Verification, Benchmarking & Acceptance Signoff**

---

## Phase Details

### Phase 1: Environment Setup, Project Layout & Ingestion Agent
- **Objective**: Establish modular codebase layout, install/verify all dependencies, copy and profile reference dataset, and implement the Ingestion Agent.
- **Tasks**:
  1. Create repository directory structure per Section 28.1.
  2. Setup `pyproject.toml`, requirements, and `.env.example`.
  3. Ingest reference dataset (`Sales Transaction v.4a.csv` ~536k rows).
  4. Build `app/agents/ingestion.py` and `app/data/bronze.py`:
     - Encoding, delimiter, header detection.
     - Schema mapping with confidence scoring and manual override support.
     - First checks profiler (Section 8.7: row counts, date ranges, nulls, distinct counts, cancellations, duplicates).
     - Capability matrix generator (Section 8.5) detecting available vs missing business features.
  5. Add unit and contract tests for ingestion and profiling.
- **Acceptance Criteria**:
  - Full ~536k row dataset profiled in under 30 seconds.
  - Column mapping matches canonical schema with high confidence.
  - Capability matrix correctly flags available fields (revenue, orders, RFM, affinity, cancellations) and unavailable fields (unit cost, stock level, ad spend).

### Phase 2: Cleaning Rule Catalog, Quarantine & Data Quality Score (DQS)
- **Objective**: Implement deterministic cleaning rules CL-01 through CL-20, user approval workflow, quarantine table, and DQS calculation with KPI distortion estimation.
- **Tasks**:
  1. Implement rule catalog in `app/data/rules/`:
     - Text normalization, ISO 8601 date parsing with ambiguous format detection.
     - Exact deduplication, cancellation tagging (`is_cancellation`), non-merchandise code isolation.
     - Bad price flagging, guest order handling (`is_guest`), bulk order flagging (`is_bulk_line`).
     - Canonical product naming by mode, country normalization.
  2. Implement silver table creation in `app/data/silver.py` and quarantine table for dropped/flagged rows.
  3. Implement Data Quality Score (Section 11) with formula:
     `DQS = 100 * (0.25*Completeness + 0.25*Validity + 0.15*Uniqueness + 0.20*Consistency + 0.15*Plausibility)`.
  4. Implement Distortion Estimator comparing raw vs clean headline KPIs (gross revenue, orders, AOV, cancellations).
  5. Add automated unit tests for cleaning rules, quarantine invariants, and DQS scoring.
- **Acceptance Criteria**:
  - Silver table generated without modifying Bronze table.
  - All rejected/quarantined records preserved in quarantine table.
  - DQS and KPI deltas computed accurately and deterministically.

### Phase 3: Semantic Layer, Gold Data Marts & DuckDB Analytics Engine
- **Objective**: Define centralized semantic metrics, build compile-time SQL generator, and materialize Gold aggregations.
- **Tasks**:
  1. Define `app/semantic/metrics.yaml` and `joins.yaml` defining:
     - `gross_revenue`, `net_revenue`, `orders`, `units`, `aov`, `units_per_order`, `customers`, `repeat_rate`, `cancellation_rate_value`, `revenue_per_customer`, `recency_days`, `frequency`, `monetary`, `abc_class`, `concentration_top10`, `country_share`, `velocity_30d`, `support`, `confidence`, `lift`.
  2. Implement `app/semantic/compiler.py` compiling metric requests into DuckDB SQL.
  3. Build Gold marts in `app/data/gold.py`: `gold_daily`, `mart_product_month`, `mart_customer_rfm`, `mart_basket_pairs`.
  4. Implement SQLite application store (`app/data/db.py`) for runs, insights, recommendations, approvals, and audit log.
- **Acceptance Criteria**:
  - Gold marts populated accurately from Silver data.
  - Semantic compiler generates valid DuckDB SQL matching definitions in Section 12.
  - Deterministic metrics reproduce exact ground-truth values.

### Phase 4: Privacy Agent, Untrusted Text Sanitizer & Hash-Chained Audit Log
- **Objective**: Implement privacy guardrails, customer identifier tokenization, injection defense, and cryptographic audit log.
- **Tasks**:
  1. Implement `app/privacy/tokenizer.py` with salted SHA-256 tokenization (`cust_XXXX`).
  2. Implement `app/privacy/scanner.py` and `app/privacy/injection.py`:
     - Scan outbound payloads for PII (emails, phone numbers, raw IDs).
     - Sanitize untrusted text fields (e.g. `product_name`) against instruction injection.
  3. Implement `app/privacy/audit.py` with SHA-256 hash chaining linking each event to `prev_hash`.
  4. Implement sandbox runner abstraction `app/tools/sandbox.py`.
  5. Test zero-leak CI gate and prompt-injection defense.
- **Acceptance Criteria**:
  - Outbound payloads contain zero unmasked customer IDs.
  - Injected instruction text in data cells is neutralized and logged as security event.
  - Audit log verifies end-to-end cryptographic integrity.

### Phase 5: Analyst Agent, Critic Agent (Self-Verification Pipeline) & Orchestrator
- **Objective**: Build the core analytical agents, the 5-layer Critic verification engine, and the multi-agent orchestrator.
- **Tasks**:
  1. Implement Analyst Agent (`app/agents/analyst.py`) translating user questions into semantic metric calls or read-only SQL, generating headline, explanation, and chart spec.
  2. Implement Critic Agent (`app/agents/critic.py`) with 5-layer verification:
     - L1 Recompute: Independent SQL formulation comparing numbers within 0.5% tolerance.
     - L2 Sanity: Checking invariant bounds (percentages 0-100%, positive order counts, sum of shares = 100%).
     - L3 Grounding: Verifying every text claim maps to queried data.
     - L4 Chart check: Ensuring chart axes, units, and series match claims.
     - L5 Rubric: Flagging causal overreach and unsupported claims.
  3. Implement confidence scoring formula and decision matrix (Pass, Pass with note, Repair loop, Block).
  4. Implement Orchestrator (`app/orchestrator/graph.py`):
     - Intent routing, budget tracking (steps, tokens, seconds, repairs), and circuit breakers.
- **Acceptance Criteria**:
  - Critic recomputes every headline figure independently.
  - Mismatched or ungrounded answers trigger repair or are blocked with safe explanation.
  - Confidence label matches formula: High (>=0.85), Medium (0.65-0.84), Low (<0.65).

### Phase 6: Forecast Agent, Diagnostic Engine & Growth Advisory Levers
- **Objective**: Implement time-series demand forecasting with backtesting, change diagnostics, and scored growth recommendations.
- **Tasks**:
  1. Implement Forecast Agent (`app/agents/forecast.py`):
     - Seasonal naive baseline, Holt-Winters / ETS, and rolling-origin backtesting.
     - 80% prediction intervals and WAPE calculation.
     - 1-year history caveat (disabled annual seasonality, low-confidence warning).
  2. Implement Diagnostic Agent (`app/agents/diagnostic.py`):
     - Hypothesis testing catalog H1-H7 (volume vs value, top product decline, country shift, cancellations, bulk buyers, calendar effects).
  3. Implement Growth Advisory Engine (`app/agents/advisor.py`):
     - Levers L1 through L10 with trigger detection and impact range estimation.
     - Priority scoring formula: `(impact_mid * confidence) / effort_points`.
     - 30-60-90 day growth action plan.
- **Acceptance Criteria**:
  - Forecast reports backtest WAPE vs seasonal naive baseline.
  - Diagnostic engine tests and ranks hypotheses with evidence.
  - Advisor outputs structured recommendation cards with impact ranges, assumptions, and measurement plans.

### Phase 7: Report Agent (HTML/PDF) & FastAPI Gateway with WebSocket Streaming
- **Objective**: Implement executive report rendering and complete REST/WebSocket API gateway.
- **Tasks**:
  1. Build Report Agent (`app/agents/report.py`):
     - Executive summary, "What happened", "What will happen", "What to do", cleaning log, DQS badge, query appendix.
     - HTML and downloadable PDF generation.
  2. Implement FastAPI gateway (`app/api/`):
     - Endpoints for upload, profile, mapping, clean, approvals, quality, chat, runs, forecast, diagnose, recommendations, reports, audit.
     - WebSocket streaming for live agent steps and verification layers.
- **Acceptance Criteria**:
  - Full API adheres to Section 22 specification.
  - WebSocket streams progress events (`agent.step`, `tool.call`, `verify.layer`, `run.completed`).
  - Reports render clean HTML and PDF in under 60 seconds.

### Phase 8: Evaluation Harness, Planted Faults & Golden Questions Suite
- **Objective**: Build reproducible evaluation harness, plant known faults, and benchmark accuracy and verification catch rate.
- **Tasks**:
  1. Build fault injection catalog (`eval/faults/`): F01-F14 (duplicates, date formats, name variants, missing IDs, cancellation spikes, prompt injection, etc.).
  2. Implement answer-corruption test suite (`eval/corruption/`) to test Critic interception.
  3. Implement golden question set (`eval/golden/`) covering 40+ questions across all types with ground-truth SQL.
  4. Build benchmark runner (`eval/runner.py`) outputting metrics against targets:
     - Cleaning accuracy >= 90%
     - Numeric correctness >= 95%
     - Critic catch rate >= 90%
     - Zero PII leaks
- **Acceptance Criteria**:
  - Evaluation harness runs end-to-end and outputs verified metrics table.
  - Zero PII leaks verified across all test runs.

### Phase 9: Interactive Modern Web UI (Dashboard, Chat, Evidence Drawer, Trust View)
- **Objective**: Deliver a premium, responsive web application implementing all screens in Section 24.
- **Tasks**:
  1. Build Web UI with modern design system:
     - Upload & Data Profile screen with Capability Matrix.
     - Cleaning Plan review with before/after diffs and DQS before/after gauge.
     - Executive Dashboard with KPI tiles, revenue trends, top products, alerts.
     - "Ask MAVIS" interactive chat with streaming agent timeline, answer cards, and "Show your work" evidence drawer.
     - Growth Advisor screen with ranked recommendation cards and 30-60-90 day plan.
     - Forecast & Diagnostics screens.
     - Trust & Audit screen with verifiable hash-chain timeline and privacy payload viewer.
- **Acceptance Criteria**:
  - All screens functional and connected to FastAPI backend.
  - Evidence drawer opens SQL and Critic second computation on tap.
  - Fully responsive, accessible, dark/light theme support.

### Phase 10: Full System Verification, Benchmarking & Acceptance Signoff
- **Objective**: Execute end-to-end integration tests, verify all SLOs and acceptance criteria, generate final documentation and runbooks.
- **Tasks**:
  1. Run full test suite (unit, integration, contract, security, evaluation).
  2. Validate all 14 User Stories (US-01 through US-14) and Functional Requirements (FR-01 through FR-34).
  3. Update `README.md`, `PROGRESS.md`, `TROUBLESHOOTING.md`.
  4. Perform clean run demonstration.
- **Acceptance Criteria**:
  - All automated tests green.
  - Demo path verified end-to-end.
  - Complete documentation and artifacts in place.
