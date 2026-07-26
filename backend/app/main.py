from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.analyze import router as analyze_router
from app.api.generate import router as generate_router
from app.api.providers import router as providers_router
from app.api.settings import router as settings_router
from app.providers.base import ProviderError
from app.config import Settings
from app.database import initialize_database


@asynccontextmanager
async def lifespan(_: FastAPI):
    defaults = Settings()
    await initialize_database(
        default_model=defaults.custom_model,
        default_api_key=defaults.custom_api_key.get_secret_value(),
    )
    yield


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
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "http_error", "message": str(exc.detail)}},
    )


app.include_router(providers_router)
app.include_router(settings_router)
app.include_router(generate_router)
app.include_router(analyze_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
