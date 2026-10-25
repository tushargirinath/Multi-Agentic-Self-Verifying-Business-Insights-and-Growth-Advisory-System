"""Answer-Corruption Test Suite for Critic Verification (Section 26.2)."""
import copy
from typing import Dict, Any, List, Tuple


class AnswerCorruptor:
    """Takes correct answer objects and deliberately injects realistic analytical faults."""

    @staticmethod
    def corrupt_drop_cancellation_filter(answer: Dict[str, Any]) -> Dict[str, Any]:
        """Corrupt gross revenue by blending in unnetted cancellations or omitting filter."""
        corrupted = copy.deepcopy(answer)
        if "gross_revenue" in corrupted.get("numbers", {}):
            corrupted["numbers"]["gross_revenue"] = float(corrupted["numbers"]["gross_revenue"]) * 1.08
            corrupted["headline"] = f"Total revenue is £{corrupted['numbers']['gross_revenue']:,.2f}."
        return corrupted

    @staticmethod
    def corrupt_inflate_number(answer: Dict[str, Any], factor: float = 1.25) -> Dict[str, Any]:
        """Inflate headline numbers by 25%."""
        corrupted = copy.deepcopy(answer)
        for k in corrupted.get("numbers", {}):
            corrupted["numbers"][k] = float(corrupted["numbers"][k]) * factor
        corrupted["headline"] = "Inflated number claim."
        return corrupted

    @staticmethod
    def corrupt_out_of_bounds_percentage(answer: Dict[str, Any]) -> Dict[str, Any]:
        """Break L2 sanity invariant by inserting an impossible percentage (> 100%)."""
        corrupted = copy.deepcopy(answer)
        corrupted["numbers"]["cancellation_rate_pct"] = 124.5
        corrupted["headline"] = "Cancellation rate reached 124.5%."
        return corrupted

    @staticmethod
    def corrupt_ungrounded_claim(answer: Dict[str, Any]) -> Dict[str, Any]:
        """Break L3 grounding by claiming an unsubstantiated surge in text."""
        corrupted = copy.deepcopy(answer)
        corrupted["headline"] = "Sales tripled by 300% in March 2019 generating £99,999,999.00."
        return corrupted

    @staticmethod
    def corrupt_causal_overreach(answer: Dict[str, Any]) -> Dict[str, Any]:
        """Break L5 rubric by asserting unproven causal certainty."""
        corrupted = copy.deepcopy(answer)
        corrupted["explanation"] = "This price change definitely caused all customers to order twice as much and proves causation."
        return corrupted


corruptor = AnswerCorruptor()
