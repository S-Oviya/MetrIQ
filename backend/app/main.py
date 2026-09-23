"""MetrIQ FastAPI application entry point."""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.database.connection import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite database tables, indexes, and directory structure on startup
    init_db()
    yield


app = FastAPI(title="MetrIQ API", version="0.1.0", lifespan=lifespan)

# --- CORS configuration ---
# Always allow the Vite dev-server origins so local development keeps working.
allowed_origins: list[str] = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

# In production, set FRONTEND_URL to the deployed frontend origin
# (e.g. "https://metriq.example.com") so the browser can reach this API.
_frontend_url = os.environ.get("FRONTEND_URL")
if _frontend_url:
    allowed_origins.append(_frontend_url.rstrip("/"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if api_router is None:  # pragma: no cover - protects against a broken router import.
    raise RuntimeError("MetrIQ API router could not be initialized.")

app.include_router(api_router)


@app.get("/health", tags=["Health"])
def health() -> dict[str, str]:
    """Return a minimal process-health response."""
    return {"status": "ok"}
