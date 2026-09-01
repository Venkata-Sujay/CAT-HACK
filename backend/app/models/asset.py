"""Asset, operator assignment history, and the immutable audit trail."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import AssetStatus, HealthState, WarehouseStatus
from app.models.tenancy import utcnow


class Asset(Base):
    """A physical machine.

    ``current_client_id`` is THE tenant key. Every client-facing query filters
    on it. NULL means the asset is unrented and belongs to the company pool.

    Runtime/idle counters exist at two granularities: lifetime totals (for
    fleet reporting) and ``*_today`` (reset at the simulated day boundary, used
    for utilisation and ML features).
    """

    __tablename__ = "assets"
    __table_args__ = (
        Index("ix_assets_client_status", "current_client_id", "status"),
        Index("ix_assets_site_status", "current_site_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    product_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    model: Mapped[str | None] = mapped_column(String(80))
    serial_number: Mapped[str | None] = mapped_column(String(64))

    status: Mapped[str] = mapped_column(String(24), default=AssetStatus.AVAILABLE.value, nullable=False, index=True)
    warehouse_status: Mapped[str] = mapped_column(
        String(24), default=WarehouseStatus.IN_WAREHOUSE.value, nullable=False
    )

    current_site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id"), index=True)
    current_client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), index=True)

    # Two distinct operator fields -- the difference between them IS the
    # UNAUTHORIZED_OPERATOR signal:
    #   assigned_employee_id  = who is AUTHORISED to operate (set by the client)
    #   current_operator_id   = who telemetry REPORTS is operating (RFID/cab login)
    assigned_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), index=True)
    current_operator_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), index=True)

    # --- live telemetry state (denormalised from telemetry_logs for fast reads) ---
    fuel_level: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)
    tire_condition: Mapped[str] = mapped_column(String(16), default=HealthState.GOOD.value, nullable=False)
    engine_condition: Mapped[str] = mapped_column(String(16), default=HealthState.GOOD.value, nullable=False)
    engine_temp_c: Mapped[float] = mapped_column(Float, default=45.0, nullable=False)
    is_running: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    runtime_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)       # lifetime
    idle_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)          # lifetime
    runtime_minutes_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    idle_minutes_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Uninterrupted running time; reset to 0 whenever the asset stops.
    continuous_runtime_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Simulated QR/RFID token. Check-in/out accepts either this or asset_code.
    qr_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    daily_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    site = relationship("Site", foreign_keys=[current_site_id])
    client = relationship("Client", foreign_keys=[current_client_id])
    assigned_employee = relationship("Employee", foreign_keys=[assigned_employee_id])
    current_operator = relationship("Employee", foreign_keys=[current_operator_id])

    @property
    def operator_match(self) -> bool:
        """True when the reported operator is the authorised one.

        Also True when no operator is reported (machine parked) -- an idle
        machine with nobody in the cab is not an authorisation violation.
        """
        if self.current_operator_id is None:
            return True
        return self.current_operator_id == self.assigned_employee_id

    @property
    def utilization(self) -> float:
        """Runtime share of engaged time today, 0.0-1.0.

        Zero denominator (asset never reported today) yields 0.0 rather than
        raising or returning NaN -- a fresh asset is 0% utilised, not undefined.

        Counters are coerced from None because SQLAlchemy applies column
        defaults at INSERT time: an Asset built in memory has None here.
        """
        runtime = self.runtime_minutes_today or 0
        idle = self.idle_minutes_today or 0
        denom = runtime + idle
        return (runtime / denom) if denom > 0 else 0.0

    @property
    def lifetime_utilization(self) -> float:
        runtime = self.runtime_minutes or 0
        idle = self.idle_minutes or 0
        denom = runtime + idle
        return (runtime / denom) if denom > 0 else 0.0

    def __repr__(self) -> str:
        return f"<Asset {self.asset_code} {self.product_type} {self.status}>"


class AssetAssignment(Base):
    """Operator-to-asset assignment history.

    ``Asset.assigned_employee_id`` is the denormalised current pointer; this
    table is the full history. Exactly one row per asset should have
    ``active=True``.
    """

    __tablename__ = "asset_assignments"
    __table_args__ = (Index("ix_assignments_asset_active", "asset_id", "active"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), nullable=False, index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    unassigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    assigned_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    asset = relationship("Asset")
    employee = relationship("Employee")


class AssetEvent(Base):
    """Immutable audit trail. Append only -- never update or delete a row here.

    Every check-in/out, assignment change and status transition writes one.
    """

    __tablename__ = "asset_events"
    __table_args__ = (Index("ix_events_asset_time", "asset_id", "timestamp"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), nullable=False, index=True)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    old_value: Mapped[str | None] = mapped_column(String(255))
    new_value: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)

    asset = relationship("Asset")
    actor = relationship("User")
