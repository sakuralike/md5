from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from password_detective.core.errors import AppError
from password_detective.db.dependencies import get_db

router = APIRouter(prefix="/health", tags=["健康检查"])


@router.get("/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready(db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise AppError("health.database_unavailable", "数据库尚未就绪", status_code=503) from exc
    return {"status": "ready", "database": "ok"}
