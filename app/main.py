from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.models.schemas import HealthResponse
from app.routers import arrange, auth

app = FastAPI(
    title="Music Arranger API",
    version="0.1.0",
    description="Backend API for AI-powered music arrangement",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(arrange.router)
app.include_router(auth.router)


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check():
    """Liveness probe — returns 200 when the service is up."""
    return HealthResponse(status="ok", version=app.version)
