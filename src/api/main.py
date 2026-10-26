"""FastAPI Main Application for Lokachakra Intelligence Graph."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import graph, hitl, ingest
from src.config import settings
from src.db.postgres import init_postgres_db

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager to verify connections and initialize schemas."""
    logger.info("Lokachakra API starting up...")
    try:
        await init_postgres_db()
        logger.info("PostgreSQL schema validated.")
    except Exception as exc:
        logger.warning("PostgreSQL schema initialization deferred or skipped", error=str(exc))
    yield
    logger.info("Lokachakra API shutting down...")


app = FastAPI(
    title="Lokachakra Intelligence Graph API",
    description="Bi-Temporal Personal Relationship & OSINT Intelligence Graph API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register route modules
app.include_router(ingest.router)
app.include_router(graph.router)
app.include_router(hitl.router)


@app.get("/health", tags=["Health"])
async def health_check():
    """Healthcheck endpoint for Docker containers and monitoring."""
    return {"status": "ok", "app": "Lokachakra"}
