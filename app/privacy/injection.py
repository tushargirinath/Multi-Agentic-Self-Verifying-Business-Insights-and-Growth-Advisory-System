"""Untrusted Text Sanitizer & Prompt-Injection Defense (Section 21.4)."""
import re
from typing import Dict, Any, Tuple


INJECTION_PATTERNS = [
    r"ignore\s+(?:all\s+)?previous\s+instructions",
    r"disregard\s+(?:all\s+)?prior\s+instructions",
    r"system\s+prompt",
    r"delete\s+database",
    r"email\s+all\s+customer\s+data",
    r"send\s+all\s+data\s+to",
    r"drop\s+table",
    r"reveal\s+(?:api\s+)?(?:secret|key|token|password)",
    r"you\s+are\s+now\s+(?:in\s+)?dan\s+mode",
    r"bypass\s+all\s+safety",
    r"format\s+disk",
    r"curl\s+http",
    r"wget\s+http",
]

COMPILED_INJECTION_REGEX = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)


class InjectionSanitizer:
    """Detects and neutralizes prompt-injection attempts inside untrusted text fields."""

    @classmethod
    def scan_and_sanitize(cls, text: str, max_length: int = 250) -> Tuple[str, bool, Dict[str, Any]]:
        """
        Inspect text for prompt-injection instructions.
        Returns:
            (sanitized_text, was_flagged, meta)
        """
        if not text:
            return "", False, {"flagged": False, "matched_patterns": []}

        text_str = str(text)
        matches = COMPILED_INJECTION_REGEX.findall(text_str)
        was_flagged = len(matches) > 0

        # Neutralize by removing or replacing dangerous instruction phrases
        cleaned_text = COMPILED_INJECTION_REGEX.sub("[FILTERED_INSTRUCTION]", text_str)

        # Wrap as quoted data literal to prevent model instruction confusion
        safe_data_text = f"\"{cleaned_text[:max_length]}\""

        meta = {
            "flagged": was_flagged,
            "matched_patterns": matches,
            "original_length": len(text_str),
            "sanitized_length": len(safe_data_text),
            "action_taken": "neutralized_and_quoted" if was_flagged else "safe_quoted"
        }

        return safe_data_text, was_flagged, meta


sanitizer = InjectionSanitizer()
