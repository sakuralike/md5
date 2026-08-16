from __future__ import annotations

import base64
import json
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from password_detective.core.config import Settings, get_settings
from password_detective.core.direct_message_crypto import (
    DirectMessageVault,
    build_direct_message_vault,
)
from password_detective.core.errors import AppError
from password_detective.core.time import utc_now
from password_detective.db.models.community import (
    CommunityDirectConversation,
    CommunityDirectConversationMember,
    CommunityDirectEventType,
    CommunityDirectMessage,
    CommunityInteractionPolicy,
    CommunityNotificationKind,
    CommunityNotificationSource,
    CommunityPublicProfile,
    CommunityUserBlock,
    CommunityUserFollow,
)
from password_detective.db.models.user import User, UserStatus
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.community.direct_message_events import (
    DirectEventDraft,
    append_direct_events,
    conversation_unread_count,
    total_direct_unread_count,
)
from password_detective.modules.community.schemas import (
    CommunityDirectConversationCreateRequest,
    CommunityDirectConversationCreateResponse,
    CommunityDirectConversationListResponse,
    CommunityDirectConversationResponse,
    CommunityDirectMemberStateResponse,
    CommunityDirectMemberStateUpdateRequest,
    CommunityDirectMessageCreateRequest,
    CommunityDirectMessageListResponse,
    CommunityDirectMessageResponse,
    CommunityDirectReadStateResponse,
    CommunityDirectReadStateUpdateRequest,
)

_DEFAULT_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 100


def create_direct_conversation(
    db: Session,
    *,
    principal: Principal,
    payload: CommunityDirectConversationCreateRequest,
) -> CommunityDirectConversationCreateResponse:
    sender = _active_user(db, principal.user.id)
    recipient = _user_by_username(db, payload.recipient_username)
    _require_direct_message_access(db, sender=sender, recipient=recipient, action="create")

    participant_low_id, participant_high_id = sorted((sender.id, recipient.id))
    existing = _conversation_by_pair(
        db,
        participant_low_id=participant_low_id,
        participant_high_id=participant_high_id,
    )
    if existing is not None:
        return CommunityDirectConversationCreateResponse(
            conversation=_conversation_response(db, conversation=existing, user_id=sender.id),
            created=False,
        )

    try:
        with db.begin_nested():
            conversation = CommunityDirectConversation(
                participant_low_id=participant_low_id,
                participant_high_id=participant_high_id,
            )
            db.add(conversation)
            db.flush()
            db.add_all(
                [
                    CommunityDirectConversationMember(
                        conversation_id=conversation.id,
                        user_id=sender.id,
                    ),
                    CommunityDirectConversationMember(
                        conversation_id=conversation.id,
                        user_id=recipient.id,
                    ),
                ]
            )
            db.flush()
    except IntegrityError:
        conversation = _conversation_by_pair(
            db,
            participant_low_id=participant_low_id,
            participant_high_id=participant_high_id,
        )
        if conversation is None:
            raise
        created = False
    else:
        created = True

    return CommunityDirectConversationCreateResponse(
        conversation=_conversation_response(db, conversation=conversation, user_id=sender.id),
        created=created,
    )


def list_direct_conversations(
    db: Session,
    *,
    principal: Principal,
    cursor: str | None,
    include_archived: bool,
    limit: int = _DEFAULT_PAGE_SIZE,
) -> CommunityDirectConversationListResponse:
    _active_user(db, principal.user.id)
    page_size = _validate_page_size(limit)
    conditions = [CommunityDirectConversationMember.user_id == principal.user.id]
    if not include_archived:
        conditions.append(CommunityDirectConversationMember.archived_at.is_(None))
    if cursor is not None:
        updated_at, conversation_id = _decode_cursor(cursor)
        conditions.append(
            or_(
                CommunityDirectConversation.updated_at < updated_at,
                (CommunityDirectConversation.updated_at == updated_at)
                & (CommunityDirectConversation.id < conversation_id),
            )
        )

    rows = db.execute(
        select(CommunityDirectConversationMember, CommunityDirectConversation)
        .join(
            CommunityDirectConversation,
            CommunityDirectConversation.id == CommunityDirectConversationMember.conversation_id,
        )
        .where(*conditions)
        .order_by(
            CommunityDirectConversation.updated_at.desc(),
            CommunityDirectConversation.id.desc(),
        )
        .limit(page_size + 1)
    ).all()
    has_more = len(rows) > page_size
    page_rows = rows[:page_size]
    items = [
        _conversation_response(
            db,
            conversation=conversation,
            user_id=principal.user.id,
            member=member,
        )
        for member, conversation in page_rows
    ]
    next_cursor = (
        _encode_cursor(page_rows[-1][1].updated_at, page_rows[-1][1].id)
        if has_more and page_rows
        else None
    )
    return CommunityDirectConversationListResponse(
        items=items,
        next_cursor=next_cursor,
        has_more=next_cursor is not None,
    )


def _require_direct_message_access(
    db: Session,
    *,
    sender: User,
    recipient: User,
    action: str,
) -> None:
    del action
    if sender.status != UserStatus.ACTIVE or recipient.status != UserStatus.ACTIVE:
        raise AppError(
            "DIRECT_MESSAGE_ACCOUNT_UNAVAILABLE",
            "私信账号当前不可用",
            status_code=403,
        )
    if sender.id == recipient.id:
        raise AppError(
            "DIRECT_MESSAGE_SELF_FORBIDDEN",
            "不能向自己发起私信",
            status_code=422,
        )
    if _users_block_each_other(db, first_user_id=sender.id, second_user_id=recipient.id):
        raise AppError(
            "DIRECT_MESSAGE_UNAVAILABLE",
            "当前无法向该用户发起私信",
            status_code=403,
        )

    profile = _ensure_public_profile(db, recipient)
    if profile.message_policy == CommunityInteractionPolicy.NOBODY:
        raise AppError(
            "DIRECT_MESSAGE_UNAVAILABLE",
            "该用户未开放私信",
            status_code=403,
        )
    if profile.message_policy == CommunityInteractionPolicy.FOLLOWING and not _is_following(
        db, follower_id=recipient.id, followed_id=sender.id
    ):
        raise AppError(
            "DIRECT_MESSAGE_UNAVAILABLE",
            "该用户仅接受已关注用户的私信",
            status_code=403,
        )


def _get_member_conversation(
    db: Session,
    *,
    conversation_id: str,
    user_id: str,
) -> CommunityDirectConversation:
    member = db.scalar(
        select(CommunityDirectConversationMember).where(
            CommunityDirectConversationMember.conversation_id == conversation_id,
            CommunityDirectConversationMember.user_id == user_id,
        )
    )
    if member is None:
        raise AppError(
            "DIRECT_MESSAGE_NOT_PARTICIPANT",
            "无权访问该私信会话",
            status_code=404,
        )
    conversation = db.get(CommunityDirectConversation, conversation_id)
    if conversation is None:
        raise AppError(
            "DIRECT_MESSAGE_NOT_PARTICIPANT",
            "无权访问该私信会话",
            status_code=404,
        )
    return conversation


def _conversation_response(
    db: Session,
    *,
    conversation: CommunityDirectConversation,
    user_id: str,
    member: CommunityDirectConversationMember | None = None,
) -> CommunityDirectConversationResponse:
    current_member = member or _get_member(
        db,
        conversation_id=conversation.id,
        user_id=user_id,
    )
    counterpart_id = (
        conversation.participant_high_id
        if conversation.participant_low_id == user_id
        else conversation.participant_low_id
    )
    counterpart = db.get(User, counterpart_id)
    if counterpart is None:
        raise AppError(
            "DIRECT_MESSAGE_ACCOUNT_UNAVAILABLE",
            "私信账号当前不可用",
            status_code=403,
        )
    profile = _ensure_public_profile(db, counterpart)
    last_message_at = db.scalar(
        select(func.max(CommunityDirectMessage.created_at)).where(
            CommunityDirectMessage.conversation_id == conversation.id
        )
    )
    unread_count = int(
        db.scalar(
            select(func.count(CommunityDirectMessage.id)).where(
                CommunityDirectMessage.conversation_id == conversation.id,
                CommunityDirectMessage.sequence > current_member.last_read_sequence,
                CommunityDirectMessage.sender_id != user_id,
            )
        )
        or 0
    )
    return CommunityDirectConversationResponse(
        id=conversation.id,
        counterpart_username=counterpart.username,
        counterpart_display_name=profile.display_name,
        counterpart_avatar_seed=profile.avatar_seed,
        counterpart_avatar_url=profile.avatar_url,
        last_message_at=last_message_at,
        unread_count=unread_count,
        last_read_sequence=current_member.last_read_sequence,
        archived_at=current_member.archived_at,
        muted_until=current_member.muted_until,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def _get_member(
    db: Session,
    *,
    conversation_id: str,
    user_id: str,
) -> CommunityDirectConversationMember:
    member = db.scalar(
        select(CommunityDirectConversationMember).where(
            CommunityDirectConversationMember.conversation_id == conversation_id,
            CommunityDirectConversationMember.user_id == user_id,
        )
    )
    if member is None:
        raise AppError(
            "DIRECT_MESSAGE_NOT_PARTICIPANT",
            "无权访问该私信会话",
            status_code=404,
        )
    return member


def _active_user(db: Session, user_id: str) -> User:
    user = db.get(User, user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        raise AppError(
            "DIRECT_MESSAGE_ACCOUNT_UNAVAILABLE",
            "私信账号当前不可用",
            status_code=403,
        )
    return user


def _user_by_username(db: Session, username: str) -> User:
    user = db.scalar(
        select(User).where(func.lower(User.username) == username.strip().lower())
    )
    if user is None or user.status != UserStatus.ACTIVE:
        raise AppError(
            "DIRECT_MESSAGE_ACCOUNT_UNAVAILABLE",
            "私信账号当前不可用",
            status_code=403,
        )
    return user


def _conversation_by_pair(
    db: Session,
    *,
    participant_low_id: str,
    participant_high_id: str,
) -> CommunityDirectConversation | None:
    return db.scalar(
        select(CommunityDirectConversation).where(
            CommunityDirectConversation.participant_low_id == participant_low_id,
            CommunityDirectConversation.participant_high_id == participant_high_id,
        )
    )


def _users_block_each_other(
    db: Session,
    *,
    first_user_id: str,
    second_user_id: str,
) -> bool:
    return (
        db.scalar(
            select(CommunityUserBlock.id).where(
                or_(
                    (CommunityUserBlock.blocker_id == first_user_id)
                    & (CommunityUserBlock.blocked_id == second_user_id),
                    (CommunityUserBlock.blocker_id == second_user_id)
                    & (CommunityUserBlock.blocked_id == first_user_id),
                )
            )
        )
        is not None
    )


def _is_following(db: Session, *, follower_id: str, followed_id: str) -> bool:
    return (
        db.scalar(
            select(CommunityUserFollow.id).where(
                CommunityUserFollow.follower_id == follower_id,
                CommunityUserFollow.followed_id == followed_id,
            )
        )
        is not None
    )


def _ensure_public_profile(db: Session, user: User) -> CommunityPublicProfile:
    profile = db.get(CommunityPublicProfile, user.id)
    if profile is None:
        profile = CommunityPublicProfile(
            user_id=user.id,
            display_name=user.username,
            avatar_seed=user.id.replace("-", "")[:24].ljust(24, "0"),
        )
        db.add(profile)
        db.flush()
    return profile


def _validate_page_size(limit: int) -> int:
    if limit < 1 or limit > _MAX_PAGE_SIZE:
        raise AppError("community.invalid_limit", "分页大小无效", status_code=422)
    return limit


def _encode_cursor(updated_at: datetime, conversation_id: str) -> str:
    normalized = updated_at.astimezone(UTC) if updated_at.tzinfo is not None else updated_at
    payload = {"updated_at": normalized.isoformat(), "id": conversation_id}
    return base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        updated_at = datetime.fromisoformat(payload["updated_at"])
        conversation_id = payload["id"]
        if not isinstance(conversation_id, str) or not conversation_id:
            raise ValueError("conversation id missing")
        return updated_at, conversation_id
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AppError("community.invalid_cursor", "分页游标无效", status_code=422) from exc


def send_direct_message(
    db: Session,
    *,
    principal: Principal,
    conversation_id: str,
    payload: CommunityDirectMessageCreateRequest,
    idempotency_key: str,
    settings: Settings | None = None,
) -> CommunityDirectMessageResponse:
    del idempotency_key
    sender = _active_user(db, principal.user.id)
    conversation = _get_member_conversation(
        db, conversation_id=conversation_id, user_id=sender.id
    )
    recipient = _counterpart_user(db, conversation=conversation, user_id=sender.id)
    _require_direct_message_access(db, sender=sender, recipient=recipient, action="send")
    vault = build_direct_message_vault(settings or get_settings())
    existing = db.scalar(
        select(CommunityDirectMessage).where(
            CommunityDirectMessage.sender_id == sender.id,
            CommunityDirectMessage.client_message_id == payload.client_message_id,
        )
    )
    if existing is not None:
        same_body = _decrypt_message(vault, existing) == payload.body
        if existing.conversation_id == conversation.id and same_body:
            return _message_response(db, message=existing, vault=vault)
        raise AppError(
            "DIRECT_MESSAGE_IDEMPOTENCY_CONFLICT",
            "客户端消息标识已用于不同的私信内容",
            status_code=409,
        )

    locked = db.scalar(
        select(CommunityDirectConversation)
        .where(CommunityDirectConversation.id == conversation.id)
        .with_for_update()
    )
    if locked is None:
        raise AppError("DIRECT_MESSAGE_NOT_PARTICIPANT", "无权访问该私信会话", status_code=404)
    encrypted = vault.encrypt(payload.body)
    sequence = int(
        db.scalar(
            select(func.max(CommunityDirectMessage.sequence)).where(
                CommunityDirectMessage.conversation_id == locked.id
            )
        )
        or 0
    ) + 1
    message = CommunityDirectMessage(
        conversation_id=locked.id,
        sender_id=sender.id,
        sequence=sequence,
        ciphertext=encrypted.ciphertext,
        nonce=encrypted.nonce,
        key_version=encrypted.key_version,
        client_message_id=payload.client_message_id,
    )
    db.add(message)
    recipient_member = _get_member(db, conversation_id=locked.id, user_id=recipient.id)
    recipient_member.archived_at = None
    locked.updated_at = utc_now()
    db.flush()

    from password_detective.modules.community.notification_service import create_notification

    create_notification(
        db,
        recipient_id=recipient.id,
        actor_id=sender.id,
        kind=CommunityNotificationKind.DIRECT_MESSAGE,
        source_type=CommunityNotificationSource.DIRECT_MESSAGE,
        source_id=message.id,
        post_id=None,
        comment_id=None,
        preview="你收到一条新私信",
        queue_event=(
            recipient_member.muted_until is None
            or recipient_member.muted_until <= utc_now()
        ),
        create_when_disabled=True,
    )
    db.flush()

    event_at = utc_now()
    message_payload = {
        "message_sequence": message.sequence,
        "sender_id": sender.id,
        "created_at": message.created_at.isoformat(),
    }
    recipient_conversation_unread = conversation_unread_count(
        db,
        user_id=recipient.id,
        conversation_id=locked.id,
    )
    recipient_total_unread = total_direct_unread_count(db, user_id=recipient.id)
    append_direct_events(
        db,
        drafts=[
            DirectEventDraft(
                recipient_id=sender.id,
                event_type=CommunityDirectEventType.MESSAGE_CREATED,
                conversation_id=locked.id,
                actor_id=sender.id,
                message_id=message.id,
                payload=message_payload,
            ),
            DirectEventDraft(
                recipient_id=recipient.id,
                event_type=CommunityDirectEventType.MESSAGE_CREATED,
                conversation_id=locked.id,
                actor_id=sender.id,
                message_id=message.id,
                payload=message_payload,
            ),
            DirectEventDraft(
                recipient_id=recipient.id,
                event_type=CommunityDirectEventType.UNREAD_CHANGED,
                conversation_id=locked.id,
                actor_id=sender.id,
                message_id=message.id,
                payload={
                    "conversation_unread_count": recipient_conversation_unread,
                    "total_unread_count": recipient_total_unread,
                    "changed_at": event_at.isoformat(),
                },
            ),
        ],
    )
    return _message_response(db, message=message, vault=vault)


def list_direct_messages(
    db: Session,
    *,
    principal: Principal,
    conversation_id: str,
    cursor: str | None,
    limit: int,
    settings: Settings | None = None,
) -> CommunityDirectMessageListResponse:
    user = _active_user(db, principal.user.id)
    conversation = _get_member_conversation(db, conversation_id=conversation_id, user_id=user.id)
    _require_existing_conversation_access(db, conversation=conversation, user_id=user.id)
    page_size = _validate_page_size(limit)
    conditions = [CommunityDirectMessage.conversation_id == conversation.id]
    if cursor is not None:
        before_sequence = _decode_message_cursor(cursor)
        conditions.append(CommunityDirectMessage.sequence < before_sequence)
    messages = db.scalars(
        select(CommunityDirectMessage)
        .where(*conditions)
        .order_by(CommunityDirectMessage.sequence.desc())
        .limit(page_size + 1)
    ).all()
    has_more = len(messages) > page_size
    page = messages[:page_size]
    vault = build_direct_message_vault(settings or get_settings())
    member = _get_member(db, conversation_id=conversation.id, user_id=user.id)
    counterpart = _counterpart_user(db, conversation=conversation, user_id=user.id)
    counterpart_member = _get_member(
        db,
        conversation_id=conversation.id,
        user_id=counterpart.id,
    )
    return CommunityDirectMessageListResponse(
        items=[_message_response(db, message=message, vault=vault) for message in page],
        next_cursor=_encode_message_cursor(page[-1].sequence) if has_more and page else None,
        has_more=has_more,
        last_read_sequence=member.last_read_sequence,
        counterpart_last_read_sequence=counterpart_member.last_read_sequence,
        unread_count=conversation_unread_count(
            db,
            user_id=user.id,
            conversation_id=conversation.id,
        ),
    )


def update_direct_read_state(
    db: Session,
    *,
    principal: Principal,
    conversation_id: str,
    payload: CommunityDirectReadStateUpdateRequest,
) -> CommunityDirectReadStateResponse:
    user = _active_user(db, principal.user.id)
    conversation = _get_member_conversation(db, conversation_id=conversation_id, user_id=user.id)
    _require_existing_conversation_access(db, conversation=conversation, user_id=user.id)
    locked = db.scalar(
        select(CommunityDirectConversation)
        .where(CommunityDirectConversation.id == conversation.id)
        .with_for_update()
    )
    if locked is None:
        raise AppError(
            "DIRECT_MESSAGE_NOT_PARTICIPANT",
            "无权访问该私信会话",
            status_code=404,
        )
    member = db.scalar(
        select(CommunityDirectConversationMember)
        .where(
            CommunityDirectConversationMember.conversation_id == locked.id,
            CommunityDirectConversationMember.user_id == user.id,
        )
        .with_for_update()
    )
    if member is None:
        raise AppError(
            "DIRECT_MESSAGE_NOT_PARTICIPANT",
            "无权访问该私信会话",
            status_code=404,
        )
    last_sequence = int(
        db.scalar(
            select(func.max(CommunityDirectMessage.sequence)).where(
                CommunityDirectMessage.conversation_id == locked.id
            )
        )
        or 0
    )
    previous_sequence = member.last_read_sequence
    next_sequence = max(previous_sequence, min(payload.last_read_sequence, last_sequence))
    member.last_read_sequence = next_sequence
    db.flush()
    unread_count = conversation_unread_count(
        db,
        user_id=user.id,
        conversation_id=locked.id,
    )
    if next_sequence > previous_sequence:
        counterpart = _counterpart_user(db, conversation=locked, user_id=user.id)
        event_at = utc_now()
        read_payload = {
            "reader_id": user.id,
            "last_read_sequence": next_sequence,
            "read_at": event_at.isoformat(),
        }
        append_direct_events(
            db,
            drafts=[
                DirectEventDraft(
                    recipient_id=user.id,
                    event_type=CommunityDirectEventType.CONVERSATION_READ,
                    conversation_id=locked.id,
                    actor_id=user.id,
                    message_id=None,
                    payload=read_payload,
                ),
                DirectEventDraft(
                    recipient_id=counterpart.id,
                    event_type=CommunityDirectEventType.CONVERSATION_READ,
                    conversation_id=locked.id,
                    actor_id=user.id,
                    message_id=None,
                    payload=read_payload,
                ),
                DirectEventDraft(
                    recipient_id=user.id,
                    event_type=CommunityDirectEventType.UNREAD_CHANGED,
                    conversation_id=locked.id,
                    actor_id=user.id,
                    message_id=None,
                    payload={
                        "conversation_unread_count": unread_count,
                        "total_unread_count": total_direct_unread_count(
                            db, user_id=user.id
                        ),
                        "changed_at": event_at.isoformat(),
                    },
                ),
            ],
        )
    return CommunityDirectReadStateResponse(
        conversation_id=locked.id,
        last_read_sequence=member.last_read_sequence,
        unread_count=unread_count,
    )


def update_direct_member_state(
    db: Session,
    *,
    principal: Principal,
    conversation_id: str,
    payload: CommunityDirectMemberStateUpdateRequest,
) -> CommunityDirectMemberStateResponse:
    user = _active_user(db, principal.user.id)
    conversation = _get_member_conversation(db, conversation_id=conversation_id, user_id=user.id)
    member = _get_member(db, conversation_id=conversation.id, user_id=user.id)
    if payload.archived is not None:
        member.archived_at = utc_now() if payload.archived else None
    if "muted_until" in payload.model_fields_set:
        member.muted_until = payload.muted_until
    db.flush()
    return CommunityDirectMemberStateResponse(
        conversation_id=conversation.id,
        archived_at=member.archived_at,
        muted_until=member.muted_until,
    )


def _require_existing_conversation_access(
    db: Session, *, conversation: CommunityDirectConversation, user_id: str
) -> None:
    counterpart = _counterpart_user(db, conversation=conversation, user_id=user_id)
    _active_user(db, counterpart.id)
    if _users_block_each_other(db, first_user_id=user_id, second_user_id=counterpart.id):
        raise AppError("DIRECT_MESSAGE_UNAVAILABLE", "当前无法访问该私信会话", status_code=403)


def _counterpart_user(
    db: Session, *, conversation: CommunityDirectConversation, user_id: str
) -> User:
    counterpart_id = (
        conversation.participant_high_id
        if conversation.participant_low_id == user_id
        else conversation.participant_low_id
    )
    counterpart = db.get(User, counterpart_id)
    if counterpart is None:
        raise AppError("DIRECT_MESSAGE_ACCOUNT_UNAVAILABLE", "私信账号当前不可用", status_code=403)
    return counterpart


def _message_response(
    db: Session, *, message: CommunityDirectMessage, vault
) -> CommunityDirectMessageResponse:
    sender = db.get(User, message.sender_id)
    if sender is None:
        raise AppError("community.direct_message_unavailable", "私信暂时无法读取", status_code=500)
    return CommunityDirectMessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        sender_username=sender.username,
        body=_decrypt_message(vault, message),
        sequence=message.sequence,
        created_at=message.created_at,
    )


def _decrypt_message(vault: DirectMessageVault, message: CommunityDirectMessage) -> str:
    return vault.decrypt(
        ciphertext=message.ciphertext,
        nonce=message.nonce,
        key_version=message.key_version,
    )


def _encode_message_cursor(sequence: int) -> str:
    return base64.urlsafe_b64encode(str(sequence).encode("ascii")).decode("ascii").rstrip("=")


def _decode_message_cursor(cursor: str) -> int:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        sequence = int(base64.urlsafe_b64decode(padded.encode("ascii")).decode("ascii"))
        if sequence < 1:
            raise ValueError("sequence is not positive")
        return sequence
    except (UnicodeDecodeError, ValueError) as exc:
        raise AppError("community.invalid_cursor", "分页游标无效", status_code=422) from exc