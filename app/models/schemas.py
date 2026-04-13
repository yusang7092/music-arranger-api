from pydantic import BaseModel
from typing import Optional


class ArrangeRequest(BaseModel):
    arrangement_id: str
    instruments: list[str]  # e.g. ["바이올린_2", "피아노"]
    mode: str               # "quick" | "thorough"
    original_filename: str = ""
    target_instrument: str = ""  # 악보를 받을 악기 (한글)
    song_title: str = ""  # 사용자가 직접 입력한 곡 제목 (레퍼런스 검색용)


class ScoreResult(BaseModel):
    instrument: str
    pdf_url: str | None = None
    png_url: str | None = None


class ArrangeStatus(BaseModel):
    id: str
    status: str             # "pending" | "processing" | "done" | "error"
    scores: list[ScoreResult] | None = None
    progress: int = 0       # 0-100
    stage: str = ""         # 현재 처리 단계 설명


class ReviseRequest(BaseModel):
    instrument: str   # Korean name, e.g. "바이올린"
    feedback: str     # User's description of what to change


class RevisionStatus(BaseModel):
    status: str       # "idle" | "revising" | "done" | "error"
    score: Optional[ScoreResult] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str
