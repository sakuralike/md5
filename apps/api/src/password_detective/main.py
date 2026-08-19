from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from password_detective.core.config import Settings, get_settings
from password_detective.core.errors import AppError, app_error_handler, validation_error_handler
from password_detective.core.http_security import HttpSecurityMiddleware
from password_detective.core.logging import configure_logging
from password_detective.core.maintenance import MaintenanceModeMiddleware
from password_detective.core.notifications import (
    NotificationGateway,
    build_notification_gateway,
)
from password_detective.core.observability import (
    ObservabilityMiddleware,
    metrics,
    refresh_runtime_metrics,
)
from password_detective.core.rate_limit import InMemoryRateLimiter, RedisRateLimiter
from password_detective.core.request_context import RequestContextMiddleware
from password_detective.db.database import Database
from password_detective.modules.account_privacy.router import router as account_privacy_router
from password_detective.modules.admin.router import router as admin_router
from password_detective.modules.archives.hash_router import router as hash_router
from password_detective.modules.archives.router import router as archives_router
from password_detective.modules.auth.router import router as auth_router
from password_detective.modules.community.admin_router import admin_router as community_admin_router
from password_detective.modules.community.boards import ensure_seed_boards
from password_detective.modules.community.router import router as community_router
from password_detective.modules.desktop_announcements.router import (
    admin_router as desktop_announcements_admin_router,
)
from password_detective.modules.desktop_announcements.router import (
    public_router as desktop_announcements_router,
)
from password_detective.modules.desktop_updates.router import (
    admin_router as desktop_updates_admin_router,
)
from password_detective.modules.desktop_updates.router import (
    public_router as desktop_updates_router,
)
from password_detective.modules.desktop_verification.router import router as desktop_router
from password_detective.modules.hash_pool.router import router as hash_pool_router
from password_detective.modules.health.router import router as health_router
from password_detective.modules.moderation.router import router as moderation_router
from password_detective.modules.reputation.router import router as reputation_router
from password_detective.modules.rewards.router import admin_router as rewards_admin_router
from password_detective.modules.rewards.router import public_router as rewards_router
from password_detective.modules.risk_alerts.router import router as risk_alerts_router
from password_detective.modules.site.router import router as site_router
from password_detective.modules.third_party_announcements.router import (
    router as third_party_announcements_router,
)
from password_detective.modules.third_party_apps.application_admin_router import (
    router as third_party_application_admin_router,
)
from password_detective.modules.third_party_apps.router import router as third_party_apps_router
from password_detective.modules.third_party_apps.user_router import (
    router as third_party_application_user_router,
)
from password_detective.modules.third_party_desktop.router import (
    router as third_party_desktop_router,
)
from password_detective.modules.third_party_hashes.router import router as third_party_hashes_router
from password_detective.modules.third_party_oauth.router import router as third_party_oauth_router
from password_detective.modules.third_party_updates.router import (
    router as third_party_updates_router,
)
from password_detective.modules.trust_cases.router import (
    admin_router as trust_cases_admin_router,
)
from password_detective.modules.trust_cases.router import user_router as trust_cases_router
from password_detective.modules.verification.router import router as verification_router
from password_detective.modules.web_announcements.router import (
    admin_router as web_announcements_admin_router,
)
from password_detective.modules.web_announcements.router import (
    public_router as web_announcements_router,
)


def create_app(
    settings: Settings | None = None,
    *,
    redis_client: Any | None = None,
    notification_gateway: NotificationGateway | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)
    database = Database(resolved_settings)
    if resolved_settings.rate_limit_backend == "redis":
        rate_limiter = (
            RedisRateLimiter(redis_client, namespace=resolved_settings.rate_limit_namespace)
            if redis_client is not None
            else RedisRateLimiter.from_url(
                resolved_settings.redis_url,
                namespace=resolved_settings.rate_limit_namespace,
            )
        )
    else:
        rate_limiter = InMemoryRateLimiter()
    notifications = notification_gateway or build_notification_gateway(resolved_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if resolved_settings.auto_create_tables:
            database.create_tables()
        with database.session_factory() as db:
            ensure_seed_boards(db)
        yield
        rate_limiter.close()
        database.dispose()

    docs_url = "/docs" if resolved_settings.app_env in {"local", "test", "integration"} else None
    app = FastAPI(
        title=resolved_settings.app_name,
        version="0.5.1",
        debug=resolved_settings.app_debug,
        docs_url=docs_url,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.database = database
    app.state.rate_limiter = rate_limiter
    app.state.notification_gateway = notifications
    app.state.logger = logging.getLogger("password_detective.http")
    app.dependency_overrides[get_settings] = lambda: resolved_settings

    app.add_middleware(
        HttpSecurityMiddleware,
        max_json_body_bytes=resolved_settings.max_json_body_bytes,
    )
    app.add_middleware(MaintenanceModeMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "Last-Event-ID",
            "X-Request-ID",
        ],
        expose_headers=["X-Request-ID", "Content-Disposition", "X-Exported-Rows"],
    )
    app.add_middleware(ObservabilityMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)

    @app.get("/api/v1/metrics", include_in_schema=False)
    def prometheus_metrics() -> Response:
        if not resolved_settings.observability_metrics_enabled:
            return Response(status_code=404)
        metrics.set_health(redis=rate_limiter.ping())
        if resolved_settings.rate_limit_backend == "redis" and redis_client is None:
            refresh_runtime_metrics(resolved_settings.redis_url)
        else:
            metrics.set_health(worker=False, queue_depth=0)
        return Response(
            content=metrics.render(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    app.include_router(health_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(site_router, prefix="/api/v1")
    app.include_router(account_privacy_router, prefix="/api/v1")
    app.include_router(admin_router, prefix="/api/v1")
    app.include_router(moderation_router, prefix="/api/v1")
    app.include_router(hash_pool_router, prefix="/api/v1")
    app.include_router(third_party_apps_router, prefix="/api/v1")
    app.include_router(third_party_application_user_router, prefix="/api/v1")
    app.include_router(third_party_application_admin_router, prefix="/api/v1")
    app.include_router(third_party_oauth_router, prefix="/api/v1")
    app.include_router(third_party_desktop_router, prefix="/api/v1")
    app.include_router(third_party_hashes_router, prefix="/api/v1")
    app.include_router(third_party_announcements_router, prefix="/api/v1")
    app.include_router(third_party_updates_router, prefix="/api/v1")
    app.include_router(trust_cases_router, prefix="/api/v1")
    app.include_router(trust_cases_admin_router, prefix="/api/v1")
    app.include_router(archives_router, prefix="/api/v1")
    app.include_router(hash_router, prefix="/api/v1")
    app.include_router(community_router, prefix="/api/v1")
    app.include_router(community_admin_router, prefix="/api/v1")
    app.include_router(verification_router, prefix="/api/v1")
    app.include_router(reputation_router, prefix="/api/v1")
    app.include_router(rewards_router, prefix="/api/v1")
    app.include_router(rewards_admin_router, prefix="/api/v1")
    app.include_router(risk_alerts_router, prefix="/api/v1")
    app.include_router(desktop_router, prefix="/api/v1")
    app.include_router(desktop_announcements_router, prefix="/api/v1")
    app.include_router(desktop_announcements_admin_router, prefix="/api/v1")
    app.include_router(web_announcements_router, prefix="/api/v1")
    app.include_router(web_announcements_admin_router, prefix="/api/v1")
    app.include_router(desktop_updates_router, prefix="/api/v1")
    app.include_router(desktop_updates_admin_router, prefix="/api/v1")
    return app


app = create_app()
