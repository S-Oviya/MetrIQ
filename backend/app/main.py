"""MetrIQ FastAPI application entry point."""

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

# The Vite development server is a separate browser origin from the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
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
