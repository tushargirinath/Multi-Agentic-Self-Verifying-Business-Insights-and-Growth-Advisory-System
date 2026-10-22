"""PII Scanner: Outbound payload inspection and zero-leak enforcement (Section 21.2)."""
import json
import re
from typing import Dict, Any, List, Tuple


EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b")
PHONE_REGEX = re.compile(r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}")
API_KEY_REGEX = re.compile(r"\b(?:sk-[a-zA-Z0-9]{20,}|key-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{20,})\b")
RAW_CUSTOMER_ID_REGEX = re.compile(r"\b(?:CustomerNo|customer_id)\s*[:=]\s*['\"]?(\d{5,})['\"]?", re.IGNORECASE)


class PIIScanner:
    """Scans outbound payloads intended for external LLM models or unsecured views."""

    @classmethod
    def scan_payload(cls, payload: Any) -> Tuple[bool, List[str]]:
        """
        Scan string or JSON structure for leaks.
        Returns:
            (is_clean, list_of_violations)
        """
        if isinstance(payload, (dict, list)):
            text = json.dumps(payload)
        else:
            text = str(payload)

        violations = []

        # 1. Emails
        emails = EMAIL_REGEX.findall(text)
        if emails:
            violations.append(f"Email detected: {emails[:3]}")

        # 2. Phone numbers
        phones = PHONE_REGEX.findall(text)
        if phones:
            violations.append(f"Phone number detected: {phones[:3]}")

        # 3. API Keys
        keys = API_KEY_REGEX.findall(text)
        if keys:
            violations.append(f"API key pattern detected")

        # 4. Raw customer numbers in prompt
        raw_cust = RAW_CUSTOMER_ID_REGEX.findall(text)
        if raw_cust:
            violations.append(f"Raw customer IDs detected in prompt: {raw_cust[:3]}")

        is_clean = len(violations) == 0
        return is_clean, violations

    @classmethod
    def enforce_zero_leak(cls, payload: Any) -> Any:
        """Enforces zero-leak policy; raises PermissionError if PII is detected."""
        is_clean, violations = cls.scan_payload(payload)
        if not is_clean:
            raise PermissionError(f"Zero-Leak Policy Violation: {'; '.join(violations)}")
        return payload


scanner = PIIScanner()
