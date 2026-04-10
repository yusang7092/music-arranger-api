from pydantic import BaseModel
from typing import Optional


class ArrangeRequest(BaseModel):
    arrangement_id: str
    instruments: list[str]  # e.g. ["바이올린_2", "피아노"]
    mode: str               # "quick" | "thorough"
    original_filename: str = ""  # 곡 검색에 활용


class ScoreResult(BaseModel):
    instrument: str
    pdf_url: str | None = None
    png_url: str | None = None


class ArrangeStatus(BaseModel):
    id: str
    status: str             # "pending" | "processing" | "done" | "error"
    scores: list[ScoreResult] | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
