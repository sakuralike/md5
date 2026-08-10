from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from password_detective.core.errors import AppError
from password_detective.core.observability import metrics
from password_detective.db.dependencies import get_db

router = APIRouter(prefix="/health", tags=["健康检查"])


@router.get("/live")
def live(request: Request) -> dict[str, str]:
    metrics.set_health(worker=None)
    return {"status": "ok"}


@router.get("/ready")
def ready(request: Request, db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
        metrics.set_health(database=True)
    except Exception as exc:
        metrics.set_health(database=False)
        raise AppError("health.database_unavailable", "数据库尚未就绪", status_code=503) from exc
    redis_ready = request.app.state.rate_limiter.ping()
    metrics.set_health(redis=redis_ready)
    if not redis_ready:
        raise AppError("health.redis_unavailable", "Redis 尚未就绪", status_code=503)
    return {"status": "ready", "database": "ok", "rate_limit": "ok"}
