from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from password_detective.db.models.user import UserRole
from password_detective.modules.auth.dependencies import Principal, require_roles

router = APIRouter(prefix="/admin", tags=["管理端"])


@router.get("/access-check")
def access_check(
    principal: Annotated[
        Principal,
        Depends(require_roles(UserRole.MODERATOR, UserRole.ADMIN)),
    ],
) -> dict[str, str]:
    """供 M1 管理端路由和 RBAC 集成验证使用。"""
    return {"status": "authorized", "role": principal.user.role.value}
