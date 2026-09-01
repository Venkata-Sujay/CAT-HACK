"""Tenancy and organisation models: Client, User, Site, Employee.

``Client`` is the tenant boundary. Every piece of client-owned data hangs off a
``client_id`` and the API layer scopes every query by it -- see
``app/core/deps.py``.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import UserRole


def utcnow() -> datetime:
    """Timezone-aware UTC now.

    ``datetime.utcnow()`` is deprecated in 3.12 and returns a naive datetime,
    which silently compares wrong against aware values. Always use this.
    """
    return datetime.now(timezone.utc)


class Client(Base):
    """A rental customer. THE tenant boundary."""

    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    contact_email: Mapped[str | None] = mapped_column(String(160))
    contact_phone: Mapped[str | None] = mapped_column(String(40))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    users: Mapped[list["User"]] = relationship(back_populates="client")
    employees: Mapped[list["Employee"]] = relationship(back_populates="client")

    def __repr__(self) -> str:
        return f"<Client {self.code}>"


class User(Base):
    """Login identity.

    Invariant enforced at creation: ``role == CLIENT`` if and only if
    ``client_id IS NOT NULL``. Company roles have no tenant and see everything.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    client: Mapped["Client | None"] = relationship(back_populates="users")

    @property
    def is_admin(self) -> bool:
        return self.role in (UserRole.COMPANY_ADMIN.value, UserRole.COMPANY_OPERATOR.value)

    def __repr__(self) -> str:
        return f"<User {self.email} ({self.role})>"


class Site(Base):
    """A physical location: a client work site, or a company warehouse.

    ``client_id IS NULL`` means the site belongs to the rental company itself
    (typically the warehouse).
    """

    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    address: Mapped[str | None] = mapped_column(String(255))
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), index=True)
    is_warehouse: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    client: Mapped["Client | None"] = relationship()

    def __repr__(self) -> str:
        return f"<Site {self.code}>"


class Employee(Base):
    """A client-side machine operator.

    Operators belong to a client, never to the rental company. The
    ``UNAUTHORIZED_OPERATOR`` rule compares telemetry's reported operator
    against the operator assigned to the asset.
    """

    __tablename__ = "employees"
    __table_args__ = (Index("ix_employees_client_active", "client_id", "active"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    employee_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(40))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    client: Mapped["Client"] = relationship(back_populates="employees")

    def __repr__(self) -> str:
        return f"<Employee {self.employee_code} {self.name}>"
