"""Privacy Tokenizer: Salted cryptographic tokenization of identifiers."""
import hashlib
from typing import Optional, Dict
from app.config import settings
from app.data.db import app_db


class PrivacyTokenizer:
    """Tokenizes sensitive identifiers before any LLM processing, keeping real IDs in secure token_vault."""

    def __init__(self, salt: Optional[str] = None):
        self.salt = salt or settings.MAVIS_TOKEN_SALT

    def tokenize_customer_id(self, customer_id: Optional[str], dataset_id: str = "ds_reference") -> Optional[str]:
        """Convert a raw customer ID into an irreversible token cust_XXXX."""
        if not customer_id or str(customer_id).strip().lower() in ("", "none", "null", "nan"):
            return None

        clean_id = str(customer_id).strip()
        # Compute SHA-256 with salt
        h = hashlib.sha256(f"{clean_id}_{self.salt}".encode("utf-8")).hexdigest()
        token = f"cust_{h[:8]}"
        id_hash = hashlib.sha256(clean_id.encode("utf-8")).hexdigest()

        # Store in token_vault
        try:
            with app_db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO token_vault (dataset_id, token, id_hash)
                    VALUES (?, ?, ?)
                """, (dataset_id, token, id_hash))
                conn.commit()
        except Exception:
            pass

        return token

    def is_token(self, val: str) -> bool:
        """Check if a string matches the token pattern cust_XXXX."""
        return isinstance(val, str) and val.startswith("cust_") and len(val) == 13


tokenizer = PrivacyTokenizer()
