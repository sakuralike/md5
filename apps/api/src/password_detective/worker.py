from __future__ import annotations

import socket

from celery import Celery
from celery.signals import heartbeat_sent, worker_ready, worker_shutdown
from redis.exceptions import RedisError

from password_detective.core.config import get_settings
from password_detective.core.notifications import build_notification_gateway
from password_detective.core.observability import (
    clear_worker_heartbeat,
    publish_worker_heartbeat,
)
from password_detective.db.database import Database
from password_detective.modules.account_privacy.service import (
    build_privacy_export,
    process_due_deletion_requests,
)
from password_detective.modules.admin.email_delivery import build_email_delivery_gateway
from password_detective.modules.community.notification_service import (
    dispatch_pending_email_digests,
    dispatch_pending_notification_events,
)
from password_detective.modules.community.search_index import dispatch_pending_search_events
from password_detective.modules.desktop_plugins.review_service import process_pending_static_reviews
from password_detective.modules.desktop_plugins.service import delete_due_remediation_versions
from password_detective.modules.rewards.service import process_pending_fulfillments
from password_detective.modules.risk_alerts.notifications import (
    dispatch_pending_notifications,
    queue_due_sla_notifications,
)
from password_detective.modules.trust_cases.notifications import (
    dispatch_pending_case_notifications,
)
from password_detective.modules.trust_cases.sla import escalate_overdue_cases

settings = get_settings()
worker_instance_id = socket.gethostname()
celery_app = Celery(
    "password_detective",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "queue-risk-alert-sla-notifications": {
            "task": "risk_alerts.queue_sla_notifications",
            "schedule": 60.0,
        },
        "dispatch-risk-alert-notifications": {
            "task": "risk_alerts.dispatch_notifications",
            "schedule": 15.0,
        },
        "dispatch-community-notification-events": {
            "task": "community.dispatch_notification_events",
            "schedule": 2.0,
        },
        "dispatch-community-email-digests": {
            "task": "community.dispatch_email_digests",
            "schedule": 120.0,
        },
        "dispatch-community-search-events": {
            "task": "community.dispatch_search_events",
            "schedule": 2.0,
        },
        "escalate-overdue-trust-cases": {
            "task": "trust_cases.escalate_overdue",
            "schedule": 60.0,
        },
        "dispatch-trust-case-notifications": {
            "task": "trust_cases.dispatch_notifications",
            "schedule": 15.0,
        },
        "process-account-deletion-requests": {
            "task": "privacy.process_deletions",
            "schedule": 300.0,
        },
        "process-reward-fulfillments": {
            "task": "rewards.process_fulfillments",
            "schedule": 5.0,
        },
        "process-desktop-plugin-static-reviews": {
            "task": "desktop_plugins.process_static_reviews",
            "schedule": 5.0,
        },
        "delete-due-plugin-remediations": {
            "task": "desktop_plugins.delete_due_remediations",
            "schedule": 300.0,
        },
    },
)


def _publish_heartbeat() -> None:
    try:
        publish_worker_heartbeat(settings.redis_url, worker_instance_id)
    except RedisError:
        return


@worker_ready.connect
def on_worker_ready(**_: object) -> None:
    _publish_heartbeat()


@heartbeat_sent.connect
def on_worker_heartbeat(**_: object) -> None:
    _publish_heartbeat()


@worker_shutdown.connect
def on_worker_shutdown(**_: object) -> None:
    try:
        clear_worker_heartbeat(settings.redis_url, worker_instance_id)
    except RedisError:
        return


@celery_app.task(name="system.ping")
def ping() -> dict[str, str]:
    return {"status": "ok"}


@celery_app.task(name="observability.noop")
def observability_noop(marker: str) -> str:
    """Drain-only synthetic task used by the WP4 queue backlog drill."""
    return marker


@celery_app.task(name="risk_alerts.queue_sla_notifications")
def queue_risk_alert_sla_notifications() -> dict[str, int]:
    database = Database(settings)
    try:
        with database.session_factory() as db:
            queued = queue_due_sla_notifications(db)
            return {"queued": queued}
    finally:
        database.dispose()


@celery_app.task(name="risk_alerts.dispatch_notifications")
def dispatch_risk_alert_notifications() -> dict[str, int]:
    database = Database(settings)
    try:
        with database.session_factory() as db:
            gateway = build_email_delivery_gateway(
                db,
                settings=settings,
                fallback=build_notification_gateway(settings),
            )
            return dispatch_pending_notifications(db, gateway)
    finally:
        database.dispose()


@celery_app.task(name="community.dispatch_notification_events")
def dispatch_community_notification_events() -> dict[str, int]:
    database = Database(settings)
    try:
        with database.session_factory() as db:
            return dispatch_pending_notification_events(db)
    finally:
        database.dispose()


@celery_app.task(name="community.dispatch_email_digests")
def dispatch_community_email_digests() -> dict[str, int]:
    database = Database(settings)
    try:
        with database.session_factory() as db:
            gateway = build_email_delivery_gateway(
                db,
                settings=settings,
                fallback=build_notification_gateway(settings),
            )
            return dispatch_pending_email_digests(db, gateway)
    finally:
        database.dispose()


@celery_app.task(name="community.dispatch_search_events")
def dispatch_community_search_events() -> dict[str, int]:
    database = Database(settings)
    try:
        with database.session_factory() as db:
            return dispatch_pending_search_events(db).as_dict()
    finally:
        database.dispose()


@celery_app.task(name="trust_cases.escalate_overdue")
def escalate_overdue_trust_cases() -> dict[str, int]:
    database = Database(settings)
    try:
        with database.session_factory() as db:
            return {"escalated": escalate_overdue_cases(db)}
    finally:
        database.dispose()


@celery_app.task(name="trust_cases.dispatch_notifications")
def dispatch_trust_case_notifications() -> dict[str, int]:
    database = Database(settings)
    try:
        with database.session_factory() as db:
            gateway = build_email_delivery_gateway(
                db,
                settings=settings,
                fallback=build_notification_gateway(settings),
            )
            return dispatch_pending_case_notifications(db, gateway)
    finally:
        database.dispose()


@celery_app.task(name="privacy.build_export")
def build_account_privacy_export(export_id: str) -> dict[str, str]:
    database = Database(settings)
    try:
        with database.session_factory() as db:
            build_privacy_export(db, settings, export_id)
            return {"export_id": export_id, "status": "processed"}
    finally:
        database.dispose()


@celery_app.task(name="privacy.process_deletions")
def process_account_deletions() -> dict[str, int]:
    database = Database(settings)
    try:
        with database.session_factory() as db:
            return {"processed": process_due_deletion_requests(db)}
    finally:
        database.dispose()


@celery_app.task(name="rewards.process_fulfillments")
def process_reward_fulfillments() -> dict[str, int]:
    database = Database(settings)
    try:
        with database.session_factory() as db:
            return process_pending_fulfillments(db, worker_id=worker_instance_id)
    finally:
        database.dispose()


@celery_app.task(name="desktop_plugins.process_static_reviews")
def process_desktop_plugin_static_reviews() -> dict[str, int]:
    database = Database(settings)
    try:
        with database.session_factory() as db:
            return process_pending_static_reviews(
                db,
                settings,
                worker_id=worker_instance_id,
            )
    finally:
        database.dispose()


@celery_app.task(name="desktop_plugins.delete_due_remediations")
def process_due_plugin_remediations() -> dict[str, int]:
    database = Database(settings)
    try:
        with database.session_factory() as db:
            return {"deleted": delete_due_remediation_versions(db)}
    finally:
        database.dispose()
