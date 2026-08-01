from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from password_detective.core.config import Settings, get_settings
from password_detective.core.errors import AppError, app_error_handler, validation_error_handler
from password_detective.core.logging import configure_logging
from password_detective.core.rate_limit import InMemoryRateLimiter
from password_detective.core.request_context import RequestContextMiddleware
from password_detective.db.database import Database
from password_detective.modules.admin.router import router as admin_router
from password_detective.modules.auth.router import router as auth_router
from password_detective.modules.health.router import router as health_router


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)
    database = Database(resolved_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if resolved_settings.auto_create_tables:
            database.create_tables()
        yield
        database.dispose()

    docs_url = "/docs" if resolved_settings.app_env in {"local", "test", "integration"} else None
    app = FastAPI(
        title=resolved_settings.app_name,
        version="0.1.0",
        debug=resolved_settings.app_debug,
        docs_url=docs_url,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.database = database
    app.state.rate_limiter = InMemoryRateLimiter()
    app.dependency_overrides[get_settings] = lambda: resolved_settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)

    app.include_router(health_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(admin_router, prefix="/api/v1")
    return app


app = create_app()
