from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from password_detective.core.errors import AppError
from password_detective.core.time import utc_now
from password_detective.db.audit import write_audit_log
from password_detective.db.models.password_candidate import CandidateStatus, PasswordCandidate
from password_detective.db.models.submission import Submission
from password_detective.db.models.trust_case import (
    TrustCase,
    TrustCaseEvent,
    TrustCaseKind,
    TrustCaseStatus,
    TrustCaseSubjectType,
)
from password_detective.db.models.user import User
from password_detective.modules.auth.context import ClientContext
from password_detective.modules.auth.dependencies import Principal
from password_detective.modules.trust_cases.schemas import (
    AccountAppealCreateRequest,
    AppealCreateRequest,
    CaseResolutionCode,
    ReportCreateRequest,
    TrustCaseDetail,
    TrustCaseEventResponse,
    TrustCaseListResponse,
    TrustCaseSummary,
    TrustCaseTransitionRequest,
    TrustCaseTransitionResponse,
)

_ALLOWED_RESOLUTION_CODES = {
    TrustCaseKind.REPORT: {
        CaseResolutionCode.REVIEW_STARTED,
        CaseResolutionCode.ACTION_TAKEN,
        CaseResolutionCode.NO_VIOLATION,
        CaseResolutionCode.INSUFFICIENT_EVIDENCE,
        CaseResolutionCode.REOPENED,
    },
    TrustCaseKind.APPEAL: {
        CaseResolutionCode.REVIEW_STARTED,
        CaseResolutionCode.INSUFFICIENT_EVIDENCE,
        CaseResolutionCode.APPEAL_UPHELD,
        CaseResolutionCode.APPEAL_DENIED,
        CaseResolutionCode.REOPENED,
    },
    # WP2 iteration 1 only opens account appeals and lets an admin begin review.
    # Final resolution must use the later atomic orchestration endpoint.
    TrustCaseKind.ACCOUNT_APPEAL: {CaseResolutionCode.REVIEW_STARTED},
}

_ALLOWED_TRANSITIONS = {
    TrustCaseStatus.OPEN: {
        TrustCaseStatus.IN_REVIEW,
        TrustCaseStatus.RESOLVED,
        TrustCaseStatus.DISMISSED,
    },
    TrustCaseStatus.IN_REVIEW: {
        TrustCaseStatus.OPEN,
        TrustCaseStatus.RESOLVED,
        TrustCaseStatus.DISMISSED,
    },
    TrustCaseStatus.RESOLVED: {TrustCaseStatus.OPEN},
    TrustCaseStatus.DISMISSED: {TrustCaseStatus.OPEN},
}


def create_report(
    db: Session,
    *,
    payload: ReportCreateRequest,
    principal: Principal,
    context: ClientContext,
) -> TrustCaseDetail:
    candidate = db.get(PasswordCandidate, payload.candidate_id)
    if candidate is None:
        raise AppError("trust.candidate_not_found", "未找到举报目标候选", status_code=404)
    case = TrustCase(
        kind=TrustCaseKind.REPORT,
        subject_type=TrustCaseSubjectType.CANDIDATE,
        reporter_id=principal.user.id,
        candidate_id=candidate.id,
        reason_code=payload.reason_code.value,
        description=payload.description,
    )
    db.add(case)
    db.flush()
    _append_event(
        db,
        case=case,
        actor_id=principal.user.id,
        previous_status=None,
        next_status=TrustCaseStatus.OPEN,
        action="report.created",
        reason_code=payload.reason_code.value,
        note=payload.description,
        request_id=context.request_id,
    )
    _audit_created(db, case=case, principal=principal, context=context)
    db.commit()
    return get_case_detail(db, case.id, viewer_id=principal.user.id)


def create_appeal(
    db: Session,
    *,
    payload: AppealCreateRequest,
    principal: Principal,
    context: ClientContext,
) -> TrustCaseDetail:
    candidate = db.get(PasswordCandidate, payload.candidate_id)
    if candidate is None:
        raise AppError("trust.candidate_not_found", "未找到申诉目标候选", status_code=404)
    if candidate.status not in {CandidateStatus.REJECTED, CandidateStatus.QUARANTINED}:
        raise AppError(
            "trust.appeal_not_available", "仅被拒绝或隔离的候选可提交申诉", status_code=409
        )
    owns_submission = db.scalar(
        select(Submission.id).where(
            Submission.candidate_id == candidate.id,
            Submission.user_id == principal.user.id,
        )
    )
    if owns_submission is None:
        raise AppError("trust.appeal_forbidden", "仅该候选的贡献者可提交申诉", status_code=403)
    if payload.related_case_id is not None:
        related = db.get(TrustCase, payload.related_case_id)
        if related is None or related.candidate_id != candidate.id:
            raise AppError(
                "trust.related_case_not_found", "关联案件不存在或目标不一致", status_code=404
            )
    case = TrustCase(
        kind=TrustCaseKind.APPEAL,
        subject_type=TrustCaseSubjectType.CANDIDATE,
        reporter_id=principal.user.id,
        candidate_id=candidate.id,
        related_case_id=payload.related_case_id,
        reason_code=payload.reason_code.value,
        description=payload.description,
    )
    db.add(case)
    db.flush()
    _append_event(
        db,
        case=case,
        actor_id=principal.user.id,
        previous_status=None,
        next_status=TrustCaseStatus.OPEN,
        action="appeal.created",
        reason_code=payload.reason_code.value,
        note=payload.description,
        request_id=context.request_id,
    )
    _audit_created(db, case=case, principal=principal, context=context)
    db.commit()
    return get_case_detail(db, case.id, viewer_id=principal.user.id)


def create_account_appeal(
    db: Session,
    *,
    payload: AccountAppealCreateRequest,
    principal: Principal,
    context: ClientContext,
) -> TrustCaseDetail:
    case = TrustCase(
        kind=TrustCaseKind.ACCOUNT_APPEAL,
        subject_type=TrustCaseSubjectType.ACCOUNT,
        reporter_id=principal.user.id,
        target_user_id=principal.user.id,
        reason_code=payload.reason_code.value,
        requested_action=payload.requested_action.value,
        description=payload.description,
        evidence_summary=payload.evidence_summary,
    )
    db.add(case)
    db.flush()
    _append_event(
        db,
        case=case,
        actor_id=principal.user.id,
        previous_status=None,
        next_status=TrustCaseStatus.OPEN,
        action="account_appeal.created",
        reason_code=payload.reason_code.value,
        note=payload.description,
        request_id=context.request_id,
    )
    _audit_created(db, case=case, principal=principal, context=context)
    db.commit()
    return get_case_detail(db, case.id, viewer_id=principal.user.id)


def list_my_cases(
    db: Session,
    *,
    principal: Principal,
    kind: TrustCaseKind | None,
    page: int,
    page_size: int,
) -> TrustCaseListResponse:
    return _list_cases(
        db,
        where=[TrustCase.reporter_id == principal.user.id],
        kind=kind,
        status=None,
        query=None,
        page=page,
        page_size=page_size,
    )


def list_admin_cases(
    db: Session,
    *,
    kind: TrustCaseKind | None,
    status: TrustCaseStatus | None,
    query: str | None,
    page: int,
    page_size: int,
) -> TrustCaseListResponse:
    return _list_cases(
        db,
        where=[],
        kind=kind,
        status=status,
        query=query,
        page=page,
        page_size=page_size,
    )


def get_case_detail(db: Session, case_id: str, *, viewer_id: str | None = None) -> TrustCaseDetail:
    case = db.scalar(
        select(TrustCase).options(selectinload(TrustCase.events)).where(TrustCase.id == case_id)
    )
    if case is None or (viewer_id is not None and case.reporter_id != viewer_id):
        raise AppError("trust.case_not_found", "未找到举报或申诉案件", status_code=404)
    reporter = db.get(User, case.reporter_id)
    assert reporter is not None
    return TrustCaseDetail(
        **_summary(case, reporter.username).model_dump(),
        events=[_event(item) for item in case.events],
    )


def transition_case(
    db: Session,
    *,
    case_id: str,
    payload: TrustCaseTransitionRequest,
    principal: Principal,
    context: ClientContext,
) -> TrustCaseTransitionResponse:
    case = db.scalar(select(TrustCase).where(TrustCase.id == case_id).with_for_update())
    if case is None:
        raise AppError("trust.case_not_found", "未找到举报或申诉案件", status_code=404)
    previous_status = case.status
    if payload.target_status == previous_status:
        raise AppError("trust.noop_transition", "案件状态没有变化", status_code=409)
    if payload.target_status not in _ALLOWED_TRANSITIONS[previous_status]:
        raise AppError("trust.invalid_transition", "不允许执行该案件状态转换", status_code=409)
    if payload.resolution_code not in _ALLOWED_RESOLUTION_CODES[case.kind]:
        raise AppError(
            "trust.resolution_not_allowed",
            "处理结果码不适用于该案件类型",
            status_code=422,
        )

    now = utc_now()
    case.status = payload.target_status
    case.updated_at = now
    if payload.target_status == TrustCaseStatus.IN_REVIEW:
        case.assigned_to_id = principal.user.id
        case.resolution_code = None
        case.resolution_note = None
        case.resolved_by_id = None
        case.resolved_at = None
    elif payload.target_status in {TrustCaseStatus.RESOLVED, TrustCaseStatus.DISMISSED}:
        case.assigned_to_id = case.assigned_to_id or principal.user.id
        case.resolved_by_id = principal.user.id
        case.resolution_code = payload.resolution_code.value
        case.resolution_note = payload.resolution_note
        case.resolved_at = now
    else:
        case.assigned_to_id = None
        case.resolved_by_id = None
        case.resolution_code = None
        case.resolution_note = None
        case.resolved_at = None

    event = _append_event(
        db,
        case=case,
        actor_id=principal.user.id,
        previous_status=previous_status,
        next_status=payload.target_status,
        action="case.transitioned",
        reason_code=payload.resolution_code.value,
        note=payload.resolution_note,
        request_id=context.request_id,
    )
    db.flush()
    write_audit_log(
        db,
        action="trust_case.transition",
        target_type="trust_case",
        target_id=case.id,
        result="success",
        actor_id=principal.user.id,
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "kind": case.kind.value,
            "subject_type": case.subject_type.value,
            "candidate_id": case.candidate_id,
            "target_user_id": case.target_user_id,
            "risk_alert_id": case.risk_alert_id,
            "previous_status": previous_status.value,
            "current_status": payload.target_status.value,
            "resolution_code": payload.resolution_code.value,
            "event_id": event.id,
        },
    )
    db.commit()
    return TrustCaseTransitionResponse(
        case_id=case.id,
        previous_status=previous_status,
        current_status=case.status,
        event_id=event.id,
        resolution_code=payload.resolution_code,
        request_id=context.request_id,
    )


def _list_cases(
    db: Session,
    *,
    where: list,
    kind: TrustCaseKind | None,
    status: TrustCaseStatus | None,
    query: str | None,
    page: int,
    page_size: int,
) -> TrustCaseListResponse:
    filters = list(where)
    if kind is not None:
        filters.append(TrustCase.kind == kind)
    if status is not None:
        filters.append(TrustCase.status == status)
    normalized_query = query.strip() if query else None
    if normalized_query:
        filters.append(
            or_(
                TrustCase.id == normalized_query,
                TrustCase.candidate_id == normalized_query,
                TrustCase.target_user_id == normalized_query,
                TrustCase.risk_alert_id == normalized_query,
                User.username.ilike(f"%{normalized_query}%"),
            )
        )
    total = (
        db.scalar(
            select(func.count(TrustCase.id))
            .join(User, User.id == TrustCase.reporter_id)
            .where(*filters)
        )
        or 0
    )
    rows = db.execute(
        select(TrustCase, User.username)
        .join(User, User.id == TrustCase.reporter_id)
        .where(*filters)
        .order_by(TrustCase.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return TrustCaseListResponse(
        items=[_summary(case, username) for case, username in rows],
        page=page,
        page_size=page_size,
        total=total,
    )


def _summary(case: TrustCase, reporter_username: str) -> TrustCaseSummary:
    return TrustCaseSummary(
        id=case.id,
        kind=case.kind,
        subject_type=case.subject_type,
        status=case.status,
        reporter_id=case.reporter_id,
        reporter_username=reporter_username,
        candidate_id=case.candidate_id,
        target_user_id=case.target_user_id,
        risk_alert_id=case.risk_alert_id,
        related_case_id=case.related_case_id,
        reason_code=case.reason_code,
        requested_action=case.requested_action,
        description=case.description,
        evidence_summary=case.evidence_summary,
        assigned_to_id=case.assigned_to_id,
        resolved_by_id=case.resolved_by_id,
        resolution_code=case.resolution_code,
        resolution_note=case.resolution_note,
        resolved_at=case.resolved_at,
        created_at=case.created_at,
        updated_at=case.updated_at,
    )


def _event(event: TrustCaseEvent) -> TrustCaseEventResponse:
    return TrustCaseEventResponse(
        id=event.id,
        actor_id=event.actor_id,
        previous_status=event.previous_status,
        next_status=event.next_status,
        action=event.action,
        reason_code=event.reason_code,
        note=event.note,
        request_id=event.request_id,
        created_at=event.created_at,
    )


def _append_event(
    db: Session,
    *,
    case: TrustCase,
    actor_id: str | None,
    previous_status: TrustCaseStatus | None,
    next_status: TrustCaseStatus,
    action: str,
    reason_code: str,
    note: str | None,
    request_id: str | None,
) -> TrustCaseEvent:
    event = TrustCaseEvent(
        case_id=case.id,
        actor_id=actor_id,
        previous_status=previous_status,
        next_status=next_status,
        action=action,
        reason_code=reason_code,
        note=note,
        request_id=request_id,
    )
    db.add(event)
    return event


def _audit_created(
    db: Session,
    *,
    case: TrustCase,
    principal: Principal,
    context: ClientContext,
) -> None:
    write_audit_log(
        db,
        action=f"trust_case.{case.kind.value}.create",
        target_type="trust_case",
        target_id=case.id,
        result="success",
        actor_id=principal.user.id,
        ip_prefix=context.ip_prefix,
        request_id=context.request_id,
        details={
            "kind": case.kind.value,
            "subject_type": case.subject_type.value,
            "candidate_id": case.candidate_id,
            "target_user_id": case.target_user_id,
            "risk_alert_id": case.risk_alert_id,
            "requested_action": case.requested_action,
            "reason_code": case.reason_code,
            "related_case_id": case.related_case_id,
        },
    )
