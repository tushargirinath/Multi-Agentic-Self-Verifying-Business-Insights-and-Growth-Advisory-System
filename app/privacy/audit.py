"""Cryptographic Hash-Chained Audit Log (Section 21.7)."""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from app.data.db import app_db


GENESIS_HASH = "0" * 64


class AuditLogger:
    """Manages immutable, append-only, cryptographic hash-chained audit logging."""

    def __init__(self, db=app_db):
        self.db = db
        self._init_table()

    def _init_table(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TIMESTAMP,
                    actor TEXT,
                    action TEXT,
                    payload_hash TEXT,
                    prev_hash TEXT,
                    entry_hash TEXT
                );
            """)
            conn.commit()

    @staticmethod
    def hash_payload(payload: Any) -> str:
        """Compute SHA-256 hash of any arbitrary payload."""
        if isinstance(payload, (dict, list)):
            serialized = json.dumps(payload, sort_keys=True)
        else:
            serialized = str(payload)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def compute_entry_hash(prev_hash: str, ts: str, actor: str, action: str, payload_hash: str) -> str:
        """Compute cryptographic block hash linking to previous entry."""
        raw = f"{prev_hash}:{ts}:{actor}:{action}:{payload_hash}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def log_event(self, actor: str, action: str, payload: Any) -> Dict[str, Any]:
        """Append an event to the hash chain."""
        payload_hash = self.hash_payload(payload)
        ts = datetime.now(timezone.utc).isoformat()

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT entry_hash FROM audit_log ORDER BY id DESC LIMIT 1;")
            last_row = cursor.fetchone()
            prev_hash = last_row["entry_hash"] if last_row else GENESIS_HASH

            entry_hash = self.compute_entry_hash(prev_hash, ts, actor, action, payload_hash)

            cursor.execute("""
                INSERT INTO audit_log (ts, actor, action, payload_hash, prev_hash, entry_hash)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (ts, actor, action, payload_hash, prev_hash, entry_hash))
            entry_id = cursor.lastrowid
            conn.commit()

        return {
            "id": entry_id,
            "ts": ts,
            "actor": actor,
            "action": action,
            "payload_hash": payload_hash,
            "prev_hash": prev_hash,
            "entry_hash": entry_hash
        }

    def verify_chain(self) -> Dict[str, Any]:
        """Verify the integrity of the entire audit chain from genesis."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, ts, actor, action, payload_hash, prev_hash, entry_hash FROM audit_log ORDER BY id ASC;")
            entries = cursor.fetchall()

        if not entries:
            return {"valid": True, "count": 0, "status": "empty"}

        expected_prev = GENESIS_HASH
        for idx, row in enumerate(entries):
            r = dict(row)
            if r["prev_hash"] != expected_prev:
                return {
                    "valid": False,
                    "broken_at_id": r["id"],
                    "reason": f"prev_hash mismatch: expected {expected_prev}, found {r['prev_hash']}"
                }

            expected_entry = self.compute_entry_hash(
                r["prev_hash"], r["ts"], r["actor"], r["action"], r["payload_hash"]
            )
            if r["entry_hash"] != expected_entry:
                return {
                    "valid": False,
                    "broken_at_id": r["id"],
                    "reason": f"entry_hash tampering detected at row {r['id']}"
                }

            expected_prev = r["entry_hash"]

        return {
            "valid": True,
            "count": len(entries),
            "status": "verified",
            "last_entry_hash": expected_prev
        }

    def get_recent_entries(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent entries for audit review."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(r) for r in cursor.fetchall()]


audit_logger = AuditLogger()
