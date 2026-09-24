from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

import app.models  # noqa: F401  (registra os modelos no metadata)
from app.api.auth import router as auth_router
from app.api.batches import router as batches_router
from app.api.dashboard import router as dashboard_router
from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.core.config import settings
from app.core.database import Base, engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title=settings.app_name, version=settings.version, lifespan=lifespan)


@app.exception_handler(HTTPException)
async def http_error_handler(_: Request, error: HTTPException):
    return JSONResponse(
        status_code=error.status_code,
        content={
            "code": f"http_{error.status_code}",
            "detail": jsonable_encoder(error.detail),
        },
        headers=error.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, error: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "code": "validation_error",
            "detail": "Os dados enviados são inválidos.",
            "errors": jsonable_encoder(error.errors()),
        },
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(documents_router, prefix="/api")
app.include_router(batches_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
