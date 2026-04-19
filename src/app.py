"""
Ten31 Thoughts - Main Application
FastAPI application with feed management, chat, and analysis endpoints.
Uses APScheduler for background tasks (StartOS requires single container).
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .db.session import init_db, get_db
from .api.feeds import router as feeds_router
from .api.notes import router as notes_router
from .api.analysis import router as analysis_router
from .api.chat import router as chat_router
from .api.episodes import router as episodes_router
from .api.search import router as search_router
from .api.upload import router as upload_router
from .api.connections import router as connections_router
from .api.connections import signals_router
from .api.digest import router as digest_router
from .api.principles import router as principles_router
from .api.resurfacing import router as resurfacing_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger(__name__)

# Background scheduler (replaces Celery for single-container StartOS deployment)
scheduler = None


def start_scheduler():
    """Start the APScheduler background task scheduler."""
    global scheduler
    from apscheduler.schedulers.background import BackgroundScheduler
    from .worker.scheduler import poll_all_feeds_job, process_analysis_job, scheduled_resurfacing_job

    scheduler = BackgroundScheduler(timezone="UTC")

    # Poll feeds daily at 5 AM UTC
    scheduler.add_job(poll_all_feeds_job, "cron", hour=5, minute=0,
                      id="poll_feeds", max_instances=1, coalesce=True)

    # v3: Connection-first analysis every minute (20 items per batch)
    scheduler.add_job(process_analysis_job, "interval", minutes=1,
                      id="process_connection", max_instances=1, coalesce=True)

    # FSRS scheduled resurfacing daily at 6 AM UTC
    scheduler.add_job(scheduled_resurfacing_job, "cron", hour=6, minute=0,
                      id="scheduled_resurfacing", max_instances=1, coalesce=True)

    scheduler.start()
    logger.info("Background scheduler started (poll=5AM, analysis=1min/20items, resurfacing=6AM)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database and background tasks on startup."""
    logger.info("Starting Ten31 Thoughts...")

    init_db()
    logger.info("Database initialized")

    start_scheduler()

    yield

    if scheduler:
        scheduler.shutdown(wait=False)
    logger.info("Ten31 Thoughts shut down.")


app = FastAPI(
    title="Ten31 Thoughts",
    description="Macro Intelligence Service — v3 connection-first architecture",
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(feeds_router)
app.include_router(notes_router)
app.include_router(analysis_router)
app.include_router(chat_router)
app.include_router(episodes_router)
app.include_router(search_router)
app.include_router(upload_router)
app.include_router(connections_router)
app.include_router(signals_router)
app.include_router(digest_router)
app.include_router(principles_router)
app.include_router(resurfacing_router)


@app.get("/api/health")
def health_check():
    """Health check endpoint for StartOS monitoring."""
    return {"status": "healthy", "service": "ten31-thoughts", "version": "3.0.0"}


@app.get("/api/status")
def system_status(session: Session = Depends(get_db)):
    """Detailed system status including feed and analysis stats."""
    from .feeds.manager import FeedManager
    manager = FeedManager(session)
    stats = manager.get_content_stats()
    return {"status": "healthy", "version": "3.0.0", "content": stats}


# Serve the React frontend — MUST be last (catches all unmatched routes)
app.mount("/", StaticFiles(directory="static", html=True), name="static")
