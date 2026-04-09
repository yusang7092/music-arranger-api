from pydantic import BaseModel
from typing import Optional


class ArrangeRequest(BaseModel):
    arrangement_id: str
    instruments: list[str]  # e.g. ["violin", "piano", "drums"]
    mode: str               # "quick" | "thorough"


class ArrangeStatus(BaseModel):
    id: str
    status: str             # "pending" | "processing" | "done" | "error"
    scores: Optional[list[dict]] = None


class HealthResponse(BaseModel):
    status: str
    version: str
