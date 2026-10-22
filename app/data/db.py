"""Application SQLite Database Manager (Section 23.2)."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
from app.config import settings


class AppDatabase:
    """Manages application relational state in SQLite."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            # Extract file path from sqlite:/// URI
            raw_url = settings.MAVIS_DB_URL
            db_path = raw_url.replace("sqlite:///", "") if raw_url.startswith("sqlite:///") else "data/mavis_app.db"
        
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Create tables per Section 23.2."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executescript("""
                CREATE TABLE IF NOT EXISTS datasets (
                    id TEXT PRIMARY KEY,
                    merchant_id TEXT,
                    name TEXT,
                    source TEXT,
                    file_hash TEXT,
                    rows INTEGER,
                    date_min DATE,
                    date_max DATE,
                    currency TEXT,
                    status TEXT,
                    quality_score REAL,
                    created_at TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS column_mappings (
                    dataset_id TEXT,
                    canonical TEXT,
                    source_col TEXT,
                    confidence REAL,
                    confirmed BOOLEAN,
                    PRIMARY KEY (dataset_id, canonical)
                );

                CREATE TABLE IF NOT EXISTS cleaning_plans (
                    id TEXT PRIMARY KEY,
                    dataset_id TEXT,
                    status TEXT,
                    created_at TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    dataset_id TEXT,
                    user_id TEXT,
                    intent TEXT,
                    question TEXT,
                    status TEXT,
                    answer JSON,
                    verification JSON,
                    tokens_in INTEGER,
                    tokens_out INTEGER,
                    seconds REAL,
                    started_at TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS run_steps (
                    run_id TEXT,
                    step INTEGER,
                    agent TEXT,
                    tool TEXT,
                    input_hash TEXT,
                    output_hash TEXT,
                    status TEXT,
                    started_at TIMESTAMP,
                    ended_at TIMESTAMP,
                    PRIMARY KEY (run_id, step)
                );

                CREATE TABLE IF NOT EXISTS queries (
                    id TEXT PRIMARY KEY,
                    run_id TEXT,
                    sql TEXT,
                    rows_returned INTEGER,
                    duration_ms INTEGER
                );

                CREATE TABLE IF NOT EXISTS insights (
                    id TEXT PRIMARY KEY,
                    dataset_id TEXT,
                    metric TEXT,
                    period TEXT,
                    finding TEXT,
                    evidence_query_id TEXT,
                    confidence REAL,
                    data_version TEXT,
                    status TEXT,
                    created_at TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS recommendations (
                    id TEXT PRIMARY KEY,
                    dataset_id TEXT,
                    lever TEXT,
                    title TEXT,
                    payload JSON,
                    priority REAL,
                    status TEXT,
                    outcome JSON,
                    created_at TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS approvals (
                    id TEXT PRIMARY KEY,
                    type TEXT,
                    payload JSON,
                    status TEXT,
                    decided_by TEXT,
                    decided_at TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY,
                    dataset_id TEXT,
                    period TEXT,
                    format TEXT,
                    path TEXT,
                    generated_at TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS token_vault (
                    dataset_id TEXT,
                    token TEXT,
                    id_hash TEXT,
                    PRIMARY KEY (dataset_id, token)
                );
            """)
            conn.commit()

    def record_run(self, run_data: Dict[str, Any]):
        """Insert or update a query run record."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO runs 
                (id, dataset_id, user_id, intent, question, status, answer, verification, tokens_in, tokens_out, seconds, started_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run_data["id"],
                run_data.get("dataset_id"),
                run_data.get("user_id", "u_default"),
                run_data.get("intent", "describe"),
                run_data.get("question", ""),
                run_data.get("status", "completed"),
                json.dumps(run_data.get("answer")),
                json.dumps(run_data.get("verification")),
                run_data.get("tokens_in", 0),
                run_data.get("tokens_out", 0),
                run_data.get("seconds", 0.0),
                run_data.get("started_at", datetime.now(timezone.utc).isoformat())
            ))
            conn.commit()

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve run state by ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM runs WHERE id = ?", (run_id,))
            row = cursor.fetchone()
            if not row:
                return None
            d = dict(row)
            d["answer"] = json.loads(d["answer"]) if d["answer"] else None
            d["verification"] = json.loads(d["verification"]) if d["verification"] else None
            return d


app_db = AppDatabase()
