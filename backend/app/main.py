from contextlib import asynccontextmanager
import asyncio
import logging
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.analyze import router as analyze_router
from app.api.auth import router as auth_router
from app.api.generate import router as generate_router
from app.api.generation_tasks import router as generation_tasks_router
from app.api.providers import router as providers_router
from app.api.settings import router as settings_router
from app.api.history import router as history_router
from app.api.projects import router as projects_router
from app.api.feedback import router as feedback_router
from app.api.admin import router as admin_router
from app.providers.base import ProviderError
from app.config import Settings
from app.database import initialize_database
from app.dependencies import get_generation_task_manager, get_history_repository


logger = logging.getLogger(__name__)
GENERATION_REAPER_INTERVAL_SECONDS = 30


async def _reap_stale_generation_tasks() -> None:
    while True:
        await asyncio.sleep(GENERATION_REAPER_INTERVAL_SECONDS)
        try:
            await get_history_repository().fail_stale_generation_tasks()
        except Exception:
            logger.exception("Failed to reap stale generation tasks")


@asynccontextmanager
async def lifespan(_: FastAPI):
    defaults = Settings()
    await initialize_database(
        default_model=defaults.custom_model,
        default_api_key=defaults.custom_api_key.get_secret_value(),
    )
    await get_history_repository().fail_stale_generation_tasks(include_queued=True)
    reaper_task = asyncio.create_task(
        _reap_stale_generation_tasks(),
        name="stale-generation-task-reaper",
    )
    try:
        yield
    finally:
        reaper_task.cancel()
        await asyncio.gather(reaper_task, return_exceptions=True)
        await get_generation_task_manager().shutdown()


app = FastAPI(title="GenImage API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ProviderError)
async def provider_error_handler(_: Request, exc: ProviderError):
    status = {
        "provider_auth": 401,
        "provider_timeout": 504,
        "provider_request": 502,
        "provider_not_found": 400,
        "provider_not_implemented": 501,
    }.get(exc.code, 502)
    return JSONResponse(status_code=status, content={"error": {"code": exc.code, "message": exc.message}})


@app.exception_handler(HTTPException)
async def http_error_handler(_: Request, exc: HTTPException):
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
            headers=exc.headers,
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "http_error", "message": str(exc.detail)}},
        headers=exc.headers,
    )


app.include_router(providers_router)
app.include_router(auth_router)
app.include_router(settings_router)
app.include_router(generate_router)
app.include_router(generation_tasks_router)
app.include_router(analyze_router)
app.include_router(history_router)
app.include_router(projects_router)
app.include_router(feedback_router)
app.include_router(admin_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/version")
async def version():
    app_version = os.getenv("APP_VERSION", "dev").strip() or "dev"
    return JSONResponse(
        content={"version": app_version},
        headers={"Cache-Control": "no-store"},
    )
