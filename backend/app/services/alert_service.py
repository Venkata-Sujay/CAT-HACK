"""Alert creation, deduplication and lifecycle.

``raise_alert`` is the ONLY supported way to create an alert. Do not insert
Alert rows directly -- you would bypass deduplication and the simulator would
flood the table within a minute of running.

Deduplication contract
----------------------
An alert is identified by ``(asset_id, type)``. While an alert for that pair is
OPEN or ACKNOWLEDGED, re-raising it UPDATES the existing row (refreshing the
description, score and reasons) instead of inserting a new one. Once RESOLVED,
its ``dedupe_key`` is set to NULL, which frees the pair so the same condition
can legitimately alert again later.

This relies on a portable SQL behaviour: a UNIQUE index permits multiple NULLs
in both SQLite and PostgreSQL. That gives us a partial unique index without
dialect-specific DDL.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Alert,
    AlertSeverity,
    AlertSource,
    AlertStatus,
    AlertType,
    AssetEvent,
    EventType,
    utcnow,
)

logger = logging.getLogger("rental.alerts")

OPEN_STATES = (AlertStatus.OPEN.value, AlertStatus.ACKNOWLEDGED.value)


def raise_alert(
    db: Session,
    *,
    asset_id: int | None,
    client_id: int | None,
    alert_type: AlertType,
    severity: AlertSeverity,
    title: str,
    description: str,
    reasons: list[str] | None = None,
    recommended_action: str | None = None,
    source: AlertSource = AlertSource.RULE,
    score: float | None = None,
    site_id: int | None = None,
    flush: bool = True,
) -> Alert:
    """Create or refresh an alert. Idempotent for a live (asset, type) pair."""
    key = Alert.make_dedupe_key(asset_id, alert_type.value)

    existing = db.execute(
        select(Alert).where(Alert.dedupe_key == key, Alert.status.in_(OPEN_STATES))
    ).scalar_one_or_none()

    if existing is not None:
        # Refresh the live facts but preserve status and acknowledgement --
        # re-firing must not silently un-acknowledge an alert an operator
        # already triaged.
        existing.description = description
        existing.reasons = reasons or []
        existing.recommended_action = recommended_action
        existing.severity = severity.value
        existing.score = score
        existing.site_id = site_id if site_id is not None else existing.site_id
        existing.updated_at = utcnow()
        if flush:
            db.flush()
        return existing

    alert = Alert(
        asset_id=asset_id,
        client_id=client_id,
        site_id=site_id,
        type=alert_type.value,
        severity=severity.value,
        title=title,
        description=description,
        reasons=reasons or [],
        recommended_action=recommended_action,
        source=source.value,
        score=score,
        status=AlertStatus.OPEN.value,
        dedupe_key=key,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(alert)

    if asset_id is not None:
        db.add(
            AssetEvent(
                asset_id=asset_id,
                client_id=client_id,
                event_type=EventType.ALERT_RAISED.value,
                new_value=alert_type.value,
                description=title,
                timestamp=utcnow(),
            )
        )
    if flush:
        db.flush()
    return alert


def auto_resolve(
    db: Session,
    *,
    asset_id: int,
    alert_type: AlertType,
    reason: str = "Condition no longer present",
) -> int:
    """Resolve live alerts of a type whose triggering condition has cleared.

    Called by the rule engine each evaluation pass: if an asset refuelled, its
    LOW_FUEL alert should disappear on its own rather than needing a human to
    dismiss a stale warning. Returns the number of alerts resolved.

    Clearing ``dedupe_key`` is what makes the pair re-alertable later.
    """
    alerts = (
        db.execute(select(Alert).where(Alert.asset_id == asset_id, Alert.type == alert_type.value, Alert.status.in_(OPEN_STATES)))
        .scalars()
        .all()
    )
    for alert in alerts:
        alert.status = AlertStatus.RESOLVED.value
        alert.resolved_at = utcnow()
        alert.updated_at = utcnow()
        alert.dedupe_key = None  # frees the (asset, type) pair
        alert.description = f"{alert.description}\n\nAuto-resolved: {reason}"
        db.add(
            AssetEvent(
                asset_id=asset_id,
                client_id=alert.client_id,
                event_type=EventType.ALERT_RESOLVED.value,
                old_value=alert_type.value,
                description=f"Auto-resolved: {reason}",
                timestamp=utcnow(),
            )
        )
    if alerts:
        db.flush()
    return len(alerts)


def acknowledge(db: Session, alert: Alert, user_id: int) -> Alert:
    if alert.status == AlertStatus.OPEN.value:
        alert.status = AlertStatus.ACKNOWLEDGED.value
        alert.acknowledged_at = utcnow()
        alert.acknowledged_by_user_id = user_id
        alert.updated_at = utcnow()
        if alert.asset_id:
            db.add(
                AssetEvent(
                    asset_id=alert.asset_id,
                    client_id=alert.client_id,
                    actor_user_id=user_id,
                    event_type=EventType.ALERT_ACK.value,
                    new_value=alert.type,
                    description=f"Acknowledged: {alert.title}",
                    timestamp=utcnow(),
                )
            )
        db.flush()
    return alert


def resolve(db: Session, alert: Alert, user_id: int) -> Alert:
    if alert.status != AlertStatus.RESOLVED.value:
        alert.status = AlertStatus.RESOLVED.value
        alert.resolved_at = utcnow()
        alert.updated_at = utcnow()
        alert.dedupe_key = None
        if alert.asset_id:
            db.add(
                AssetEvent(
                    asset_id=alert.asset_id,
                    client_id=alert.client_id,
                    actor_user_id=user_id,
                    event_type=EventType.ALERT_RESOLVED.value,
                    old_value=alert.type,
                    description=f"Resolved: {alert.title}",
                    timestamp=utcnow(),
                )
            )
        db.flush()
    return alert


def severity_sort_key(alert: Alert) -> tuple:
    """Action-queue ordering: severity first, then most recent."""
    created = alert.created_at
    ts = created.timestamp() if created else 0
    return (AlertSeverity(alert.severity).rank, -ts)
