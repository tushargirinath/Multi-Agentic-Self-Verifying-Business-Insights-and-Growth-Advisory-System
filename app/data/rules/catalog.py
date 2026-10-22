"""Cleaning Rule Catalog (CL-01 to CL-20) and Rule Definitions."""
from typing import Dict, Any, List
from pydantic import BaseModel


class CleaningRule(BaseModel):
    rule_id: str
    name: str
    description: str
    mode: str  # "auto", "approve", "ask"
    risk: str  # "low", "medium", "high"
    default_enabled: bool = True


CLEANING_CATALOG: Dict[str, CleaningRule] = {
    "CL-01": CleaningRule(
        rule_id="CL-01",
        name="Normalize Text",
        description="Trim leading/trailing whitespace, collapse multiple spaces, title-case product names, keep raw.",
        mode="auto",
        risk="low",
    ),
    "CL-02": CleaningRule(
        rule_id="CL-02",
        name="Parse Dates",
        description="Detect date format (%m/%d/%Y vs %d/%m/%Y) and convert to standard ISO 8601 (YYYY-MM-DD).",
        mode="auto",
        risk="medium",
    ),
    "CL-03": CleaningRule(
        rule_id="CL-03",
        name="Remove Exact Duplicates",
        description="Identify identical rows across all transaction fields. Retain one copy and quarantine duplicates.",
        mode="approve",
        risk="medium",
    ),
    "CL-04": CleaningRule(
        rule_id="CL-04",
        name="Flag Cancellations",
        description="Detect cancellation prefix 'C' or negative quantities. Tag row_class='cancellation' and is_cancellation=True.",
        mode="auto",
        risk="low",
    ),
    "CL-05": CleaningRule(
        rule_id="CL-05",
        name="Separate Non-Merchandise",
        description="Identify postage, fees, manual adjustments or banking charges. Classify as row_class='non_merchandise'.",
        mode="approve",
        risk="medium",
    ),
    "CL-06": CleaningRule(
        rule_id="CL-06",
        name="Flag Bad Prices",
        description="Flag rows where unit price is zero or negative for sales. Quarantine or exclude from pricing metrics.",
        mode="approve",
        risk="medium",
    ),
    "CL-07": CleaningRule(
        rule_id="CL-07",
        name="Guest Order Handling",
        description="Tag orders with missing customer IDs as is_guest=True. Preserve in revenue, exclude from customer metrics.",
        mode="auto",
        risk="low",
    ),
    "CL-08": CleaningRule(
        rule_id="CL-08",
        name="Bulk Order Flagging",
        description="Flag transaction lines where quantity exceeds the 99th percentile for that SKU (is_bulk_line=True).",
        mode="auto",
        risk="low",
    ),
    "CL-09": CleaningRule(
        rule_id="CL-09",
        name="Canonical Product Names",
        description="Reconcile SKUs with multiple variant descriptions to the statistical mode name.",
        mode="approve",
        risk="medium",
    ),
    "CL-10": CleaningRule(
        rule_id="CL-10",
        name="Name Collisions",
        description="Flag distinct SKUs sharing the exact same product name for review.",
        mode="approve",
        risk="medium",
    ),
    "CL-11": CleaningRule(
        rule_id="CL-11",
        name="Currency Setting",
        description="Set GBP baseline currency assumption when no currency column is present.",
        mode="auto",
        risk="low",
    ),
    "CL-12": CleaningRule(
        rule_id="CL-12",
        name="Country Normalization",
        description="Normalize country names, trim casing variants, and map missing countries to 'Unspecified'.",
        mode="auto",
        risk="low",
    ),
    "CL-13": CleaningRule(
        rule_id="CL-13",
        name="Recompute Line Totals",
        description="Compute line_total strictly as unit_price * quantity (signed, negative for cancellations).",
        mode="auto",
        risk="low",
    ),
    "CL-14": CleaningRule(
        rule_id="CL-14",
        name="Date Range Bounds Check",
        description="Quarantine rows where parsed dates fall outside historical plausibility bounds.",
        mode="approve",
        risk="medium",
    ),
    "CL-15": CleaningRule(
        rule_id="CL-15",
        name="Type Coercion",
        description="Safely cast strings to integer quantities and decimal prices. Quarantine unparseable records.",
        mode="auto",
        risk="low",
    ),
}
