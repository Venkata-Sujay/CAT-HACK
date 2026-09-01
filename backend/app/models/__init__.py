"""ORM model registry.

Importing this package registers every mapper on ``Base.metadata``. Anything
that calls ``Base.metadata.create_all()`` must import this first, or it will
create an empty schema.
"""

from app.models.alert import Alert
from app.models.asset import Asset, AssetAssignment, AssetEvent
from app.models.enums import (
    AlertSeverity,
    AlertSource,
    AlertStatus,
    AlertType,
    AssetStatus,
    EventType,
    HealthState,
    ProductType,
    RecommendationStatus,
    RecommendationType,
    RentalStatus,
    UserRole,
    WarehouseStatus,
)
from app.models.intelligence import Forecast, Recommendation
from app.models.rental import Rental
from app.models.telemetry import TelemetryLog
from app.models.tenancy import Client, Employee, Site, User, utcnow

__all__ = [
    "Alert",
    "AlertSeverity",
    "AlertSource",
    "AlertStatus",
    "AlertType",
    "Asset",
    "AssetAssignment",
    "AssetEvent",
    "AssetStatus",
    "Client",
    "Employee",
    "EventType",
    "Forecast",
    "HealthState",
    "ProductType",
    "Recommendation",
    "RecommendationStatus",
    "RecommendationType",
    "Rental",
    "RentalStatus",
    "Site",
    "TelemetryLog",
    "User",
    "UserRole",
    "WarehouseStatus",
    "utcnow",
]
