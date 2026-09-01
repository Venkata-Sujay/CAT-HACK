"""Rental agreements -- the check-out / check-in record."""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import RentalStatus
from app.models.tenancy import utcnow


class Rental(Base):
    """One rental agreement for one asset.

    Invariant: at most one ACTIVE (or OVERDUE) rental per asset at a time.
    Enforced in ``services/rental_service.py`` -- a partial unique index would
    need dialect-specific SQL, so the service layer owns it and a test proves it.
    """

    __tablename__ = "rentals"
    __table_args__ = (
        Index("ix_rentals_asset_status", "asset_id", "status"),
        Index("ix_rentals_client_status", "client_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), nullable=False, index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id"), index=True)

    checkout_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    expected_return_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    actual_return_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[str] = mapped_column(String(16), default=RentalStatus.ACTIVE.value, nullable=False, index=True)
    rental_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    checkout_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    checkin_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    checkin_condition_notes: Mapped[str | None] = mapped_column(Text)

    asset = relationship("Asset")
    client = relationship("Client")
    site = relationship("Site")

    @property
    def is_open(self) -> bool:
        return self.status in (RentalStatus.ACTIVE.value, RentalStatus.OVERDUE.value)

    def __repr__(self) -> str:
        return f"<Rental asset={self.asset_id} client={self.client_id} {self.status}>"
