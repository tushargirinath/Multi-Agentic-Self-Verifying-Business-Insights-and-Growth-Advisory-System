"""Orchestrator Run State definition (Section 14.1)."""
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class BudgetConfig(BaseModel):
    max_steps: int = 12
    max_tokens: int = 60000
    max_seconds: int = 90
    max_repairs: int = 3


class SpentTracker(BaseModel):
    steps: int = 0
    tokens: int = 0
    seconds: float = 0.0
    repairs: int = 0


class RunState(BaseModel):
    run_id: str
    dataset_id: str = "ds_reference"
    user_id: str = "u_default"
    intent: str = "describe"
    question: str = ""
    status: str = "pending"  # pending, running, completed, repaired, blocked, failed
    plan: List[Dict[str, Any]] = Field(default_factory=list)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    spent: SpentTracker = Field(default_factory=SpentTracker)
    artifacts: Dict[str, Any] = Field(default_factory=lambda: {"queries": [], "charts": [], "tables": []})
    assumptions: List[str] = Field(default_factory=list)
    answer: Optional[Dict[str, Any]] = None
    verification: Optional[Dict[str, Any]] = None
    privacy: Dict[str, Any] = Field(default_factory=lambda: {"masked_fields": ["customer_id"], "leak_scan": "pass"})
    trace: List[Dict[str, Any]] = Field(default_factory=list)
