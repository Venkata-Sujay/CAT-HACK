"""Schemas for client onboarding.

One request creates a tenant, its login, its sites and its opening equipment
allocation. Kept in its own module because it is the only place in the API
where a single call writes across five tables, and that deserves to be obvious
from the import list rather than buried in domain.py.
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import ProductType


class OnboardingSite(BaseModel):
    """A site to create for the new client."""

    name: str = Field(min_length=2, max_length=160)
    address: str | None = Field(default=None, max_length=255)
    # Defaults put an unspecified site in the Hyderabad operating region the
    # rest of the demo data sits in, so a new client still lands on the map.
    latitude: float = Field(default=17.45, ge=-90, le=90)
    longitude: float = Field(default=78.40, ge=-180, le=180)


class OnboardingEquipmentLine(BaseModel):
    """How many of one equipment type this client is taking."""

    product_type: ProductType
    quantity: int = Field(ge=1, le=25)


class ClientOnboardingRequest(BaseModel):
    """Register a new client, its login, its sites and its opening fleet."""

    name: str = Field(min_length=2, max_length=160)
    code: str | None = Field(default=None, max_length=16)
    contact_email: str | None = Field(default=None, max_length=160)
    contact_phone: str | None = Field(default=None, max_length=32)

    # Login for the client portal. Plain `str` for the email rather than
    # EmailStr for the same reason as the login route: the demo tenants use the
    # reserved `.local` TLD, which EmailStr rejects.
    login_email: str = Field(min_length=3, max_length=160)
    login_password: str = Field(min_length=8, max_length=128)
    login_full_name: str = Field(min_length=2, max_length=160)

    sites: list[OnboardingSite] = Field(default_factory=list, max_length=5)
    equipment: list[OnboardingEquipmentLine] = Field(default_factory=list, max_length=5)
    rental_days: int = Field(default=30, ge=1, le=365)

    @field_validator("login_email", "contact_email")
    @classmethod
    def _looks_like_an_address(cls, value: str | None) -> str | None:
        # Deliberately minimal. This is an admin creating an account, not a
        # login, so rejecting a malformed address here leaks nothing.
        if value is None:
            return None
        cleaned = value.strip()
        if cleaned and "@" not in cleaned:
            raise ValueError("must contain @")
        return cleaned

    @field_validator("equipment")
    @classmethod
    def _no_duplicate_types(
        cls, value: list[OnboardingEquipmentLine]
    ) -> list[OnboardingEquipmentLine]:
        seen = {line.product_type for line in value}
        if len(seen) != len(value):
            raise ValueError("each equipment type may appear only once")
        return value


class AllocatedAsset(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    asset_id: int
    asset_code: str
    product_type: str
    model: str | None = None
    site_code: str | None = None
    rental_id: int


class OnboardedSite(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    latitude: float
    longitude: float


class InventoryLine(BaseModel):
    """Warehouse availability for one equipment type."""

    product_type: str
    available: int
    total: int


class ClientOnboardingResponse(BaseModel):
    """What the wizard shows on its success screen.

    Note what is NOT here: the password. It went in, it was hashed, and it is
    never echoed back -- not even to the admin who just typed it.
    """

    client_id: int
    client_name: str
    client_code: str
    login_email: str
    user_id: int
    sites: list[OnboardedSite]
    allocated: list[AllocatedAsset]
    inventory_after: list[InventoryLine]
    expected_return_at: str
