"""Application entry point.

Run locally:   uvicorn app.main:app --reload
On Azure:      startup.sh (gunicorn + uvicorn workers)
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.db import SessionLocal, init_db
from app.routers import api, budgets, categories, expenses, pages
from app.seed import seed_starter_categories
from app.templating import templates

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if settings.seed_on_first_run:
        with SessionLocal() as session:
            seed_starter_categories(session)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(pages.router)
app.include_router(expenses.router)
app.include_router(categories.router)
app.include_router(budgets.router)
app.include_router(api.router)


@app.exception_handler(StarletteHTTPException)
async def friendly_error(request: Request, exc: StarletteHTTPException):
    """Show form validation problems as a page rather than raw JSON."""
    if request.headers.get("accept", "").startswith("application/json"):
        raise exc
    return templates.TemplateResponse(
        request,
        "error.html",
        {"page": "", "status": exc.status_code, "detail": exc.detail},
        status_code=exc.status_code,
    )


@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"status": "ok"}
