from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from password_detective.core.errors import AppError
from password_detective.db.models.community import CommunityBoard, CommunityBoardStatus
from password_detective.db.models.user import UserRole

SEED_BOARDS: tuple[tuple[str, str, str, int], ...] = (
    ("general", "社区广场", "交流安全恢复经验、工具使用方式与协作建议。", 10),
    ("recovery_guides", "恢复指南", "分享合法授权场景下的恢复流程与排障记录。", 20),
    ("verification", "验证协作", "讨论指纹、候选结果与验证证据，不发布真实密码。", 30),
    ("security", "安全与隐私", "交流账号保护、数据最小化与隐私实践。", 40),
)

ROLE_RANK: dict[UserRole, int] = {
    UserRole.USER: 0,
    UserRole.TRUSTED_CONTRIBUTOR: 1,
    UserRole.MODERATOR: 2,
    UserRole.ADMIN: 3,
    UserRole.SERVICE: -1,
}


def ensure_seed_boards(db: Session) -> None:
    existing = set(db.scalars(select(CommunityBoard.code)).all())
    for code, name, description, sort_order in SEED_BOARDS:
        if code not in existing:
            db.add(
                CommunityBoard(
                    code=code,
                    name=name,
                    description=description,
                    sort_order=sort_order,
                    minimum_role=UserRole.USER.value,
                    status=CommunityBoardStatus.ACTIVE,
                    is_read_only=False,
                )
            )
    if len(existing) < len(SEED_BOARDS):
        db.commit()


def get_board_by_code(db: Session, code: str, *, include_inactive: bool = False) -> CommunityBoard:
    ensure_seed_boards(db)
    conditions = [CommunityBoard.code == code]
    if not include_inactive:
        conditions.append(CommunityBoard.status == CommunityBoardStatus.ACTIVE)
    board = db.scalar(select(CommunityBoard).where(*conditions))
    if board is None:
        raise AppError("community.board_not_found", "社区板块不存在或已停用", status_code=404)
    return board


def require_board_post_access(board: CommunityBoard, role: UserRole) -> None:
    if board.is_read_only:
        raise AppError("community.board_read_only", "该板块当前为只读状态", status_code=403)
    try:
        minimum_role = UserRole(board.minimum_role)
    except ValueError as exc:
        raise AppError(
            "community.board_configuration_invalid", "板块权限配置无效", status_code=500
        ) from exc
    if ROLE_RANK.get(role, -1) < ROLE_RANK.get(minimum_role, 0):
        raise AppError(
            "community.board_role_required",
            "当前账号角色不满足该板块的发帖要求",
            status_code=403,
            details={"minimum_role": minimum_role.value},
        )
