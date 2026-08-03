from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from password_detective.db.models.evidence_correlation import EvidenceCorrelationAssessment
from password_detective.db.models.verification import CandidateFeedback, FeedbackOutcome

CORRELATION_RULE_VERSION = "correlation-v1"


@dataclass(frozen=True)
class CorrelationGroup:
    ordinal: int
    feedback_ids: tuple[str, ...]
    user_ids: tuple[str, ...]
    shared_signals: tuple[str, ...]
    success_count: int
    failure_count: int
    raw_success_weight: float
    effective_success_weight: float
    raw_failure_weight: float
    effective_failure_weight: float

    @property
    def member_count(self) -> int:
        return len(self.feedback_ids)


@dataclass(frozen=True)
class CorrelationAnalysis:
    groups: tuple[CorrelationGroup, ...]
    feedback_count: int
    independent_group_count: int
    correlated_group_count: int
    downweighted_feedback_count: int
    independent_success_count: int
    independent_failure_count: int
    raw_success_weight: float
    effective_success_weight: float
    raw_failure_weight: float
    effective_failure_weight: float


class _DisjointSet:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))
        self.rank = [0] * size

    def find(self, value: int) -> int:
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def union(self, left: int, right: int) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        if self.rank[left_root] < self.rank[right_root]:
            left_root, right_root = right_root, left_root
        self.parent[right_root] = left_root
        if self.rank[left_root] == self.rank[right_root]:
            self.rank[left_root] += 1


def analyze_feedback_correlations(
    feedbacks: list[CandidateFeedback],
) -> CorrelationAnalysis:
    """Build connected components across shared installation and IP signals.

    Raw correlation identifiers are used only in memory. Callers may expose account and feedback
    identifiers to MFA-protected reviewers, but must never serialize the raw signal values.
    """

    ordered = sorted(
        enumerate(feedbacks),
        key=lambda pair: (pair[1].id or "", pair[0]),
    )
    ordered_feedbacks = [feedback for _, feedback in ordered]
    feedback_identifiers = {
        id(feedback): feedback.id or f"unpersisted-{index + 1:04d}"
        for index, feedback in enumerate(ordered_feedbacks)
    }
    ordered = ordered_feedbacks
    if not ordered:
        return CorrelationAnalysis(
            groups=(),
            feedback_count=0,
            independent_group_count=0,
            correlated_group_count=0,
            downweighted_feedback_count=0,
            independent_success_count=0,
            independent_failure_count=0,
            raw_success_weight=0.0,
            effective_success_weight=0.0,
            raw_failure_weight=0.0,
            effective_failure_weight=0.0,
        )

    disjoint = _DisjointSet(len(ordered))
    signal_owners: dict[tuple[str, str], int] = {}
    for index, feedback in enumerate(ordered):
        signals = []
        if feedback.installation_id_hash:
            signals.append(("installation", feedback.installation_id_hash))
        if feedback.ip_prefix:
            signals.append(("ip_prefix", feedback.ip_prefix))
        for signal in signals:
            owner = signal_owners.setdefault(signal, index)
            disjoint.union(index, owner)

    components: dict[int, list[CandidateFeedback]] = defaultdict(list)
    for index, feedback in enumerate(ordered):
        components[disjoint.find(index)].append(feedback)

    groups: list[CorrelationGroup] = []
    downweighted_feedback_count = 0
    for ordinal, members in enumerate(
        sorted(
            components.values(),
            key=lambda items: min(feedback_identifiers[id(item)] for item in items),
        ),
        start=1,
    ):
        installation_counts = Counter(
            item.installation_id_hash for item in members if item.installation_id_hash
        )
        ip_counts = Counter(item.ip_prefix for item in members if item.ip_prefix)
        shared_signals: list[str] = []
        if any(count > 1 for count in installation_counts.values()):
            shared_signals.append("installation")
        if any(count > 1 for count in ip_counts.values()):
            shared_signals.append("ip_prefix")

        success_weights = [
            item.weight for item in members if item.outcome == FeedbackOutcome.SUCCESS
        ]
        failure_weights = [
            item.weight for item in members if item.outcome == FeedbackOutcome.FAILURE
        ]
        downweighted_feedback_count += max(len(success_weights) - 1, 0)
        downweighted_feedback_count += max(len(failure_weights) - 1, 0)
        groups.append(
            CorrelationGroup(
                ordinal=ordinal,
                feedback_ids=tuple(
                    sorted(feedback_identifiers[id(item)] for item in members)
                ),
                user_ids=tuple(sorted(item.user_id for item in members)),
                shared_signals=tuple(shared_signals),
                success_count=len(success_weights),
                failure_count=len(failure_weights),
                raw_success_weight=sum(success_weights),
                effective_success_weight=max(success_weights, default=0.0),
                raw_failure_weight=sum(failure_weights),
                effective_failure_weight=max(failure_weights, default=0.0),
            )
        )

    return CorrelationAnalysis(
        groups=tuple(groups),
        feedback_count=len(ordered),
        independent_group_count=len(groups),
        correlated_group_count=sum(group.member_count > 1 for group in groups),
        downweighted_feedback_count=downweighted_feedback_count,
        independent_success_count=sum(group.success_count > 0 for group in groups),
        independent_failure_count=sum(group.failure_count > 0 for group in groups),
        raw_success_weight=sum(group.raw_success_weight for group in groups),
        effective_success_weight=sum(group.effective_success_weight for group in groups),
        raw_failure_weight=sum(group.raw_failure_weight for group in groups),
        effective_failure_weight=sum(group.effective_failure_weight for group in groups),
    )


def persist_correlation_assessment(
    db: Session,
    *,
    candidate_id: str,
    trigger_evidence_id: str,
    analysis: CorrelationAnalysis,
) -> EvidenceCorrelationAssessment:
    assessment = EvidenceCorrelationAssessment(
        candidate_id=candidate_id,
        trigger_evidence_id=trigger_evidence_id,
        rule_version=CORRELATION_RULE_VERSION,
        feedback_count=analysis.feedback_count,
        independent_group_count=analysis.independent_group_count,
        correlated_group_count=analysis.correlated_group_count,
        downweighted_feedback_count=analysis.downweighted_feedback_count,
        raw_success_weight=analysis.raw_success_weight,
        effective_success_weight=analysis.effective_success_weight,
        raw_failure_weight=analysis.raw_failure_weight,
        effective_failure_weight=analysis.effective_failure_weight,
    )
    db.add(assessment)
    db.flush()
    return assessment


def list_correlation_assessments(
    db: Session,
    candidate_id: str,
) -> list[EvidenceCorrelationAssessment]:
    return list(
        db.scalars(
            select(EvidenceCorrelationAssessment)
            .where(EvidenceCorrelationAssessment.candidate_id == candidate_id)
            .order_by(EvidenceCorrelationAssessment.created_at.desc())
        )
    )
