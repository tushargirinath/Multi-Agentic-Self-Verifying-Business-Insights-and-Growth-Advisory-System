"""Bronze Data Layer: Raw, immutable ingestion and hashing."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional
import duckdb
from app.config import settings


class BronzeManager:
    """Manages the raw, immutable Bronze data layer."""

    def __init__(self, duckdb_conn: Optional[duckdb.DuckDBPyConnection] = None):
        self.con = duckdb_conn or duckdb.connect(settings.duckdb_path)
        self._init_tables()

    def _init_tables(self):
        """Initialize the bronze tables per Section 23.1 of MAVIS spec."""
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS bronze_raw_sales (
                dataset_id VARCHAR,
                row_id BIGINT,
                raw JSON,
                loaded_at TIMESTAMP
            );
        """)
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS bronze_files (
                dataset_id VARCHAR PRIMARY KEY,
                file_path VARCHAR,
                file_hash VARCHAR,
                file_size_bytes BIGINT,
                row_count BIGINT,
                created_at TIMESTAMP
            );
        """)

    @staticmethod
    def compute_file_hash(file_path: str) -> str:
        """Compute SHA-256 hash of the input raw file for immutability and auditability."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def load_raw_csv_to_bronze(self, file_path: str, dataset_id: str = "ds_reference") -> Dict[str, Any]:
        """Ingest raw CSV file into bronze layer without altering content."""
        file_hash = self.compute_file_hash(file_path)
        file_size = Path(file_path).stat().st_size
        now = datetime.now(timezone.utc)

        # Create a dedicated raw table for this dataset for fast querying
        raw_table_name = f"bronze_raw_{dataset_id}"
        self.con.execute(f"DROP TABLE IF EXISTS {raw_table_name}")
        self.con.execute(f"""
            CREATE TABLE {raw_table_name} AS 
            SELECT row_number() OVER () AS row_id, * 
            FROM read_csv('{file_path}', all_varchar=true)
        """)

        row_count = self.con.execute(f"SELECT COUNT(*) FROM {raw_table_name}").fetchone()[0]

        # Record file metadata
        self.con.execute("""
            INSERT OR REPLACE INTO bronze_files 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (dataset_id, str(file_path), file_hash, file_size, row_count, now))

        return {
            "dataset_id": dataset_id,
            "raw_table": raw_table_name,
            "file_path": str(file_path),
            "file_hash": file_hash,
            "file_size_bytes": file_size,
            "row_count": row_count,
            "loaded_at": now.isoformat()
        }
