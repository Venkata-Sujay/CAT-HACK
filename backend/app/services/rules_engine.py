"""Deterministic rule engine.

These conditions are FACTS, not predictions, so they are evaluated with explicit
thresholds rather than a model. A missed unauthorized-operator alert because a
model scored it 0.51 would be indefensible; ML earns only the fuzzy cases
(see ``app/ml/anomaly.py``).

Rules implemented
-----------------
1. UNAUTHORIZED_OPERATOR  - running with an operator who is not the assigned one
2. UNASSIGNED_EQUIPMENT   - rented but no site and/or no operator on record
3. CONTINUOUS_USAGE       - operating beyond the configured continuous window
4. UNDERUTILIZED          - rented but effectively no productive runtime
5. LOW_FUEL               - fuel below threshold
6. TIRE_WARNING           - tire condition degraded
7. ENGINE_WARNING         - engine condition degraded
8. DUE_SOON / OVERDUE     - rental deadline approaching or passed

Every rule is self-clearing: when its condition stops holding, the matching
alert auto-resolves. Stale warnings that need manual dismissal train operators
to ignore the queue.

Threshold note: CONTINUOUS_USAGE is a configurable OPERATIONAL RECOMMENDATION
for the demo, not a certified machinery safety limit, and the UI says so.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    AlertSeverity,
    AlertSource,
    AlertType,
    Asset,
    AssetStatus,
    Employee,
    HealthState,
    Rental,
    RentalStatus,
)
from app.services.alert_service import auto_resolve, raise_alert
from app.services.asset_service import OPEN_RENTAL_STATES, hours_until, is_deployed

logger = logging.getLogger("rental.rules")


def _fmt_hours(minutes: int) -> str:
    return f"{minutes / 60:.1f}h"


def evaluate_asset(db: Session, asset: Asset, rental: Rental | None = None) -> int:
    """Run every rule against one asset. Returns the number of alerts raised.

    Safe to call on every telemetry tick -- alert deduplication in
    ``alert_service.raise_alert`` makes repeated firing idempotent.
    """
    raised = 0
    client_id = asset.current_client_id
    site_id = asset.current_site_id
    deployed = is_deployed(asset)

    # An asset already withdrawn for maintenance is expected to have degraded
    # components -- that is why it is there. Alerting on it would put a
    # permanent, un-actionable row in the action queue for every machine in the
    # workshop. Clear anything outstanding and stop.
    if asset.status == AssetStatus.MAINTENANCE.value:
        for alert_type in (
            AlertType.TIRE_WARNING,
            AlertType.ENGINE_WARNING,
            AlertType.LOW_FUEL,
            AlertType.CONTINUOUS_USAGE,
            AlertType.UNDERUTILIZED,
            AlertType.UNASSIGNED_EQUIPMENT,
            AlertType.DUE_SOON,
            AlertType.OVERDUE,
        ):
            auto_resolve(db, asset_id=asset.id, alert_type=alert_type, reason="Asset is in maintenance")
        return 0

    if rental is None and deployed:
        rental = db.execute(
            select(Rental).where(Rental.asset_id == asset.id, Rental.status.in_(OPEN_RENTAL_STATES))
        ).scalars().first()

    # ------------------------------------------------------------------
    # 1. UNAUTHORIZED_OPERATOR (CRITICAL)
    #
    # Simulated identity check: telemetry reports who is in the cab
    # (RFID badge / cab login). If that differs from the assigned operator
    # while the machine is running, someone unauthorised is operating it.
    # No computer vision involved -- mismatch comes from the operator ID.
    # ------------------------------------------------------------------
    reported_operator_id = asset.current_operator_id
    if asset.is_running and reported_operator_id is not None and asset.assigned_employee_id is not None:
        if reported_operator_id != asset.assigned_employee_id:
            actual = db.get(Employee, reported_operator_id)
            expected = db.get(Employee, asset.assigned_employee_id)
            actual_label = f"{actual.employee_code} ({actual.name})" if actual else "an unregistered operator"
            expected_label = f"{expected.employee_code} ({expected.name})" if expected else "the assigned operator"
            raise_alert(
                db,
                asset_id=asset.id,
                client_id=client_id,
                site_id=site_id,
                alert_type=AlertType.UNAUTHORIZED_OPERATOR,
                severity=AlertSeverity.CRITICAL,
                title=f"Unauthorized operator on {asset.asset_code}",
                description=(
                    f"{asset.asset_code} is running under {actual_label}, "
                    f"but {expected_label} is the registered operator for this machine."
                ),
                reasons=[
                    f"Telemetry reports operator {actual_label}",
                    f"Registered operator is {expected_label}",
                    "Machine is currently running",
                ],
                recommended_action="Contact the site supervisor to verify who is operating this machine, or update the operator assignment.",
                source=AlertSource.RULE,
            )
            raised += 1
        else:
            auto_resolve(db, asset_id=asset.id, alert_type=AlertType.UNAUTHORIZED_OPERATOR,
                         reason="Assigned operator is now operating the machine")

    # ------------------------------------------------------------------
    # 2. UNASSIGNED_EQUIPMENT (HIGH)
    # Rented equipment with no site or no operator is equipment nobody is
    # accountable for -- the classic "lost machine" in the problem statement.
    # ------------------------------------------------------------------
    if deployed:
        gaps = []
        if asset.current_site_id is None:
            gaps.append("no site assigned")
        if asset.assigned_employee_id is None:
            gaps.append("no operator assigned")
        if gaps:
            raise_alert(
                db,
                asset_id=asset.id,
                client_id=client_id,
                site_id=site_id,
                alert_type=AlertType.UNASSIGNED_EQUIPMENT,
                severity=AlertSeverity.HIGH,
                title=f"{asset.asset_code} is unaccounted for",
                description=(
                    f"{asset.asset_code} is checked out but has {' and '.join(gaps)}. "
                    "Equipment without a site or operator on record cannot be tracked or held accountable."
                ),
                reasons=[f"Asset is checked out ({asset.status})"] + [g.capitalize() for g in gaps],
                recommended_action="Assign the machine to a site and a registered operator, or check it back in.",
                source=AlertSource.RULE,
            )
            raised += 1
        else:
            auto_resolve(db, asset_id=asset.id, alert_type=AlertType.UNASSIGNED_EQUIPMENT,
                         reason="Site and operator are now assigned")

    # ------------------------------------------------------------------
    # 3. CONTINUOUS_USAGE (MEDIUM)
    # ------------------------------------------------------------------
    threshold = settings.CONTINUOUS_USAGE_THRESHOLD_MINUTES
    if asset.continuous_runtime_minutes >= threshold:
        raise_alert(
            db,
            asset_id=asset.id,
            client_id=client_id,
            site_id=site_id,
            alert_type=AlertType.CONTINUOUS_USAGE,
            severity=AlertSeverity.MEDIUM,
            title=f"{asset.asset_code} has been operating continuously for {_fmt_hours(asset.continuous_runtime_minutes)}",
            description=(
                f"{asset.asset_code} has run for {_fmt_hours(asset.continuous_runtime_minutes)} without a break, "
                f"exceeding the configured {_fmt_hours(threshold)} review threshold. "
                "This is a configurable operational guideline, not a certified machinery limit."
            ),
            reasons=[
                f"Continuous runtime: {_fmt_hours(asset.continuous_runtime_minutes)}",
                f"Configured review threshold: {_fmt_hours(threshold)}",
            ],
            recommended_action="Consider scheduling a rest or inspection period for this machine.",
            source=AlertSource.RULE,
        )
        raised += 1
    else:
        # Resolve as soon as continuous runtime drops back under the threshold,
        # not only at exactly zero -- otherwise a machine that paused briefly
        # would keep a stale alert until it fully reset.
        auto_resolve(db, asset_id=asset.id, alert_type=AlertType.CONTINUOUS_USAGE,
                     reason="Continuous runtime is back within the review threshold")

    # ------------------------------------------------------------------
    # 4. UNDERUTILIZED (MEDIUM)
    # Paying rent for a machine that is not producing anything.
    # ------------------------------------------------------------------
    if deployed:
        engaged = asset.runtime_minutes_today + asset.idle_minutes_today
        if engaged >= settings.UNDERUTILIZED_WINDOW_MINUTES and (
            asset.runtime_minutes_today <= settings.UNDERUTILIZED_MAX_RUNTIME_MINUTES
        ):
            raise_alert(
                db,
                asset_id=asset.id,
                client_id=client_id,
                site_id=site_id,
                alert_type=AlertType.UNDERUTILIZED,
                severity=AlertSeverity.MEDIUM,
                title=f"{asset.asset_code} has had almost no productive runtime",
                description=(
                    f"{asset.asset_code} has recorded only {_fmt_hours(asset.runtime_minutes_today)} of runtime "
                    f"against {_fmt_hours(asset.idle_minutes_today)} idle today "
                    f"({asset.utilization * 100:.0f}% utilization) while under active rental."
                ),
                reasons=[
                    f"Runtime today: {_fmt_hours(asset.runtime_minutes_today)}",
                    f"Idle today: {_fmt_hours(asset.idle_minutes_today)}",
                    f"Utilization: {asset.utilization * 100:.0f}%",
                ],
                recommended_action="Investigate the reason, reassign the asset to an active task, or return it if it is no longer needed.",
                source=AlertSource.RULE,
            )
            raised += 1
        elif asset.runtime_minutes_today > settings.UNDERUTILIZED_MAX_RUNTIME_MINUTES:
            auto_resolve(db, asset_id=asset.id, alert_type=AlertType.UNDERUTILIZED,
                         reason="Productive runtime has resumed")

    # ------------------------------------------------------------------
    # 5. LOW_FUEL (MEDIUM)
    # ------------------------------------------------------------------
    if asset.fuel_level < settings.LOW_FUEL_THRESHOLD:
        severity = AlertSeverity.HIGH if asset.fuel_level < 10 else AlertSeverity.MEDIUM
        raise_alert(
            db,
            asset_id=asset.id,
            client_id=client_id,
            site_id=site_id,
            alert_type=AlertType.LOW_FUEL,
            severity=severity,
            title=f"{asset.asset_code} fuel at {asset.fuel_level:.0f}%",
            description=(
                f"{asset.asset_code} has {asset.fuel_level:.0f}% fuel remaining, "
                f"below the {settings.LOW_FUEL_THRESHOLD:.0f}% threshold."
            ),
            reasons=[
                f"Fuel level: {asset.fuel_level:.0f}%",
                f"Alert threshold: {settings.LOW_FUEL_THRESHOLD:.0f}%",
            ],
            recommended_action="Schedule refuelling before the machine stops mid-task.",
            source=AlertSource.RULE,
            score=asset.fuel_level,
        )
        raised += 1
    else:
        auto_resolve(db, asset_id=asset.id, alert_type=AlertType.LOW_FUEL, reason="Machine has been refuelled")

    # ------------------------------------------------------------------
    # 6 & 7. TIRE_WARNING / ENGINE_WARNING
    # ------------------------------------------------------------------
    for condition, alert_type, label in (
        (asset.tire_condition, AlertType.TIRE_WARNING, "Tire"),
        (asset.engine_condition, AlertType.ENGINE_WARNING, "Engine"),
    ):
        if condition == HealthState.GOOD.value:
            auto_resolve(db, asset_id=asset.id, alert_type=alert_type, reason=f"{label} condition restored to GOOD")
            continue

        severity = AlertSeverity.CRITICAL if condition == HealthState.CRITICAL.value else AlertSeverity.HIGH
        raise_alert(
            db,
            asset_id=asset.id,
            client_id=client_id,
            site_id=site_id,
            alert_type=alert_type,
            severity=severity,
            title=f"{asset.asset_code} {label.lower()} condition is {condition}",
            description=(
                f"{label} condition on {asset.asset_code} has degraded to {condition}. "
                + (
                    "Continued operation risks failure and unplanned downtime."
                    if condition == HealthState.CRITICAL.value
                    else "Monitor closely and plan a service window."
                )
            ),
            reasons=[
                f"{label} condition: {condition}",
                f"Machine is {'running' if asset.is_running else 'not running'}",
            ],
            recommended_action=(
                f"Withdraw the machine from service and inspect the {label.lower()} immediately."
                if condition == HealthState.CRITICAL.value
                else f"Schedule a {label.lower()} inspection at the next opportunity."
            ),
            source=AlertSource.RULE,
        )
        raised += 1

    # ------------------------------------------------------------------
    # 8. DUE_SOON / OVERDUE
    # ------------------------------------------------------------------
    if rental is not None and rental.status in OPEN_RENTAL_STATES:
        hours_left = hours_until(rental.expected_return_at)
        if hours_left is not None:
            if hours_left < 0:
                days_over = abs(hours_left) / 24
                raise_alert(
                    db,
                    asset_id=asset.id,
                    client_id=client_id,
                    site_id=site_id,
                    alert_type=AlertType.OVERDUE,
                    severity=AlertSeverity.HIGH if days_over > 2 else AlertSeverity.MEDIUM,
                    title=f"{asset.asset_code} is overdue by {days_over:.1f} days",
                    description=(
                        f"{asset.asset_code} was due back on "
                        f"{rental.expected_return_at:%Y-%m-%d %H:%M} and has not been checked in."
                    ),
                    reasons=[
                        f"Expected return: {rental.expected_return_at:%Y-%m-%d %H:%M}",
                        f"Overdue by: {days_over:.1f} days",
                    ],
                    recommended_action="Contact the client to arrange return, or extend the rental agreement.",
                    source=AlertSource.RULE,
                    score=hours_left,
                )
                raised += 1
                auto_resolve(db, asset_id=asset.id, alert_type=AlertType.DUE_SOON,
                             reason="Rental is now overdue (escalated)")
                if rental.status != RentalStatus.OVERDUE.value:
                    rental.status = RentalStatus.OVERDUE.value
                if asset.status != AssetStatus.OVERDUE.value:
                    asset.status = AssetStatus.OVERDUE.value

            elif hours_left <= settings.DUE_SOON_HOURS:
                raise_alert(
                    db,
                    asset_id=asset.id,
                    client_id=client_id,
                    site_id=site_id,
                    alert_type=AlertType.DUE_SOON,
                    severity=AlertSeverity.LOW,
                    title=f"{asset.asset_code} is due back in {hours_left:.0f}h",
                    description=(
                        f"{asset.asset_code} is scheduled for return on "
                        f"{rental.expected_return_at:%Y-%m-%d %H:%M} ({hours_left:.0f} hours from now)."
                    ),
                    reasons=[
                        f"Expected return: {rental.expected_return_at:%Y-%m-%d %H:%M}",
                        f"Time remaining: {hours_left:.0f} hours",
                    ],
                    recommended_action="Confirm return logistics with the client, or extend the rental if the machine is still needed.",
                    source=AlertSource.RULE,
                    score=hours_left,
                )
                raised += 1
            else:
                auto_resolve(db, asset_id=asset.id, alert_type=AlertType.DUE_SOON,
                             reason="Return deadline is no longer imminent")
    else:
        # Not on rental any more -- clear any deadline alerts.
        auto_resolve(db, asset_id=asset.id, alert_type=AlertType.DUE_SOON, reason="Rental closed")
        auto_resolve(db, asset_id=asset.id, alert_type=AlertType.OVERDUE, reason="Rental closed")

    return raised


def evaluate_all(db: Session, commit: bool = True) -> dict:
    """Run the rule engine across the whole fleet.

    Called after each simulator tick and by the seed script.
    """
    assets = db.execute(select(Asset)).scalars().all()
    total = 0
    for asset in assets:
        try:
            total += evaluate_asset(db, asset)
        except Exception:  # noqa: BLE001 - one bad asset must not stop the sweep
            logger.exception("Rule evaluation failed for asset %s", asset.asset_code)
    if commit:
        db.commit()
    return {"assets_evaluated": len(assets), "alerts_raised": total}
