"""Forecast and recommendation records -- the PREDICT and RECOMMEND stages."""

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import RecommendationStatus
from app.models.tenancy import utcnow


class Forecast(Base):
    """Predicted demand for one (site, product_type, date).

    Persisted rather than computed per-request so the dashboard stays fast and
    so a demo shows stable numbers rather than values that shift between clicks.
    """

    __tablename__ = "forecasts"
    __table_args__ = (Index("ix_forecast_site_type_date", "site_id", "product_type", "forecast_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id"), nullable=False, index=True)
    product_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    forecast_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    horizon_days: Mapped[int] = mapped_column(Integer, default=7, nullable=False)

    predicted_demand: Mapped[float] = mapped_column(Float, nullable=False)
    currently_available: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expected_shortfall: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    model_version: Mapped[str | None] = mapped_column(String(64))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    site = relationship("Site")

    def __repr__(self) -> str:
        return f"<Forecast site={self.site_id} {self.product_type} {self.forecast_date} d={self.predicted_demand:.1f}>"


class Recommendation(Base):
    """An actionable suggestion produced by the rule-based recommendation engine.

    ``client_id IS NULL`` means a company-level recommendation (e.g. pre-position
    warehouse stock). Otherwise it is scoped to that tenant.

    ``rationale`` holds the numbers behind the suggestion so the UI can show
    *why*, not just *what*.
    """

    __tablename__ = "recommendations"
    __table_args__ = (Index("ix_reco_client_status", "client_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), index=True)
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id"), index=True)
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"), index=True)

    type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[list | None] = mapped_column(JSON, default=list)

    product_type: Mapped[str | None] = mapped_column(String(32))
    quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    status: Mapped[str] = mapped_column(
        String(16), default=RecommendationStatus.OPEN.value, nullable=False, index=True
    )
    dedupe_key: Mapped[str | None] = mapped_column(String(128), unique=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    client = relationship("Client")
    site = relationship("Site")
    asset = relationship("Asset")

    def __repr__(self) -> str:
        return f"<Recommendation {self.type} client={self.client_id} qty={self.quantity}>"
