"""Alerts -- the output of the hybrid rule + ML intelligence layer."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import AlertStatus
from app.models.tenancy import utcnow


class Alert(Base):
    """An actionable finding about an asset.

    ``dedupe_key`` is load-bearing. The simulator ticks every ~10 seconds; without
    deduplication a single low-fuel asset would insert thousands of identical rows
    within minutes and the action queue would be unusable.

    The mechanism relies on a portable SQL detail: **a UNIQUE index permits
    multiple NULLs** in both SQLite and PostgreSQL. So:

      * OPEN / ACKNOWLEDGED alert -> dedupe_key = "{asset_id}:{type}" (unique,
        blocks a duplicate being raised)
      * RESOLVED alert            -> dedupe_key = NULL (frees the key so the same
        condition can legitimately alert again later)

    This gives us a partial unique index without dialect-specific DDL.

    ``reasons`` and ``recommended_action`` are first-class columns, not an
    afterthought: an alert that cannot explain itself is not actionable. We never
    surface a bare model score to a user.
    """

    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_client_status", "client_id", "status"),
        Index("ix_alerts_asset_status", "asset_id", "status"),
        Index("ix_alerts_dedupe", "dedupe_key", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"), index=True)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), index=True)
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id"), index=True)

    type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Human-readable explanation, e.g.
    # ["Runtime is 87% below this asset's normal range", "Idle time high for 3 periods"]
    reasons: Mapped[list | None] = mapped_column(JSON, default=list)
    recommended_action: Mapped[str | None] = mapped_column(Text)

    source: Mapped[str] = mapped_column(String(16), nullable=False)
    score: Mapped[float | None] = mapped_column(Float)

    status: Mapped[str] = mapped_column(String(16), default=AlertStatus.OPEN.value, nullable=False, index=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(96))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    asset = relationship("Asset")
    client = relationship("Client")
    site = relationship("Site")

    @staticmethod
    def make_dedupe_key(asset_id: int | None, alert_type: str) -> str:
        return f"{asset_id}:{alert_type}"

    def __repr__(self) -> str:
        return f"<Alert {self.type} {self.severity} asset={self.asset_id} {self.status}>"
