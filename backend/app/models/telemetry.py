"""Telemetry time series -- the raw signal the whole platform reasons over."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.tenancy import utcnow


class TelemetryLog(Base):
    """One telemetry tick from one asset.

    ``current_operator_id`` is the operator the machine *reports* -- simulating
    an RFID badge or cab login. Comparing it against
    ``Asset.assigned_employee_id`` is what powers the UNAUTHORIZED_OPERATOR
    alert. No computer vision involved; identity mismatch is simulated.

    Deltas (not absolutes) are stored for runtime/idle so the series can be
    aggregated over any window without double counting.
    """

    __tablename__ = "telemetry_logs"
    __table_args__ = (Index("ix_telemetry_asset_time", "asset_id", "timestamp"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), nullable=False, index=True)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)

    runtime_delta_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    idle_delta_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    fuel_level: Mapped[float] = mapped_column(Float, nullable=False)
    tire_health: Mapped[str] = mapped_column(String(16), nullable=False)
    engine_health: Mapped[str] = mapped_column(String(16), nullable=False)
    engine_temp_c: Mapped[float] = mapped_column(Float, default=45.0, nullable=False)

    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id"), index=True)

    current_operator_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), index=True)
    is_running: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    asset = relationship("Asset")
    operator = relationship("Employee")

    def __repr__(self) -> str:
        return f"<Telemetry asset={self.asset_id} @{self.timestamp} running={self.is_running}>"
