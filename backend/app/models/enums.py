"""Domain vocabulary.

Every enum inherits ``str`` so values serialise as plain strings in JSON and
store as TEXT in any database. This is what keeps the schema portable between
SQLite and PostgreSQL: no native ENUM type means no ``ALTER TYPE`` migration
pain when we add a status later.
"""

from enum import Enum


class UserRole(str, Enum):
    COMPANY_ADMIN = "COMPANY_ADMIN"
    COMPANY_OPERATOR = "COMPANY_OPERATOR"
    CLIENT = "CLIENT"


class ProductType(str, Enum):
    EXCAVATOR = "EXCAVATOR"
    BULLDOZER = "BULLDOZER"
    CRANE = "CRANE"
    GRADER = "GRADER"
    WHEEL_LOADER = "WHEEL_LOADER"


class AssetStatus(str, Enum):
    """Lifecycle state of a physical asset.

    Transitions are explicit and owned by ``services/asset_status.py``. Nothing
    else should assign this field directly.

        AVAILABLE  --checkout-->  RENTED
        RENTED     --telemetry--> ACTIVE / IDLE   (running or not)
        ACTIVE|IDLE --deadline--> OVERDUE
        any        --maintenance--> MAINTENANCE
        MAINTENANCE --end-->      AVAILABLE
        any        --checkin-->   AVAILABLE
    """

    AVAILABLE = "AVAILABLE"      # in warehouse, rentable
    RENTED = "RENTED"            # checked out, no telemetry yet
    ACTIVE = "ACTIVE"            # rented and currently running
    IDLE = "IDLE"                # rented but not running
    OVERDUE = "OVERDUE"          # past expected_return_at, not checked in
    MAINTENANCE = "MAINTENANCE"  # withdrawn from service
    UNKNOWN = "UNKNOWN"          # no telemetry for an extended period


class WarehouseStatus(str, Enum):
    IN_WAREHOUSE = "IN_WAREHOUSE"
    DEPLOYED = "DEPLOYED"
    IN_TRANSIT = "IN_TRANSIT"
    MAINTENANCE = "MAINTENANCE"


class HealthState(str, Enum):
    """Component condition.

    Degrades monotonically GOOD -> WARNING -> CRITICAL. It never improves on its
    own; only an explicit maintenance action resets it. Flickering health would
    make every alert meaningless.
    """

    GOOD = "GOOD"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"

    @property
    def numeric(self) -> int:
        return {"GOOD": 0, "WARNING": 1, "CRITICAL": 2}[self.value]

    def degraded(self) -> "HealthState":
        """Next step down the degradation ladder. CRITICAL is absorbing."""
        order = [HealthState.GOOD, HealthState.WARNING, HealthState.CRITICAL]
        return order[min(order.index(self) + 1, len(order) - 1)]


class RentalStatus(str, Enum):
    ACTIVE = "ACTIVE"
    RETURNED = "RETURNED"
    OVERDUE = "OVERDUE"
    CANCELLED = "CANCELLED"


class AlertType(str, Enum):
    CONTINUOUS_USAGE = "CONTINUOUS_USAGE"
    UNDERUTILIZED = "UNDERUTILIZED"
    LOW_FUEL = "LOW_FUEL"
    TIRE_WARNING = "TIRE_WARNING"
    ENGINE_WARNING = "ENGINE_WARNING"
    DUE_SOON = "DUE_SOON"
    OVERDUE = "OVERDUE"
    UNAUTHORIZED_OPERATOR = "UNAUTHORIZED_OPERATOR"
    UNASSIGNED_EQUIPMENT = "UNASSIGNED_EQUIPMENT"
    ML_ANOMALY = "ML_ANOMALY"
    FORECAST_SHORTFALL = "FORECAST_SHORTFALL"


class AlertSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"

    @property
    def rank(self) -> int:
        """Sort weight for the action queue. Lower sorts first."""
        return {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}[self.value]


class AlertStatus(str, Enum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


class AlertSource(str, Enum):
    RULE = "RULE"      # deterministic business rule
    ML = "ML"          # IsolationForest
    HYBRID = "HYBRID"  # rule confirmed by model, or vice versa


class EventType(str, Enum):
    CHECKOUT = "CHECKOUT"
    CHECKIN = "CHECKIN"
    ASSIGN_OPERATOR = "ASSIGN_OPERATOR"
    UNASSIGN_OPERATOR = "UNASSIGN_OPERATOR"
    STATUS_CHANGE = "STATUS_CHANGE"
    SITE_CHANGE = "SITE_CHANGE"
    MAINTENANCE_START = "MAINTENANCE_START"
    MAINTENANCE_END = "MAINTENANCE_END"
    ALERT_RAISED = "ALERT_RAISED"
    ALERT_ACK = "ALERT_ACK"
    ALERT_RESOLVED = "ALERT_RESOLVED"
    ASSET_CREATED = "ASSET_CREATED"


class RecommendationType(str, Enum):
    REQUEST_MORE_ASSETS = "REQUEST_MORE_ASSETS"
    PREPOSITION_ASSET = "PREPOSITION_ASSET"
    RETURN_UNDERUTILIZED = "RETURN_UNDERUTILIZED"
    SCHEDULE_MAINTENANCE = "SCHEDULE_MAINTENANCE"
    REASSIGN_OPERATOR = "REASSIGN_OPERATOR"


class RecommendationStatus(str, Enum):
    OPEN = "OPEN"
    REQUESTED = "REQUESTED"
    ACCEPTED = "ACCEPTED"
    DISMISSED = "DISMISSED"
