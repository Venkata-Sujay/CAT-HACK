"""Auth request/response contracts."""

from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    """JSON login body. The OAuth2 form endpoint is also supported.

    ``email`` is a plain ``str``, deliberately NOT ``EmailStr``:

    * Format-validating a login identifier leaks information -- a 422 for
      "malformed" versus a 401 for "wrong credentials" tells an attacker which
      addresses are even shaped like real accounts. Every failed login should
      look identical.
    * ``EmailStr`` also rejects reserved TLDs, which would block the documented
      demo accounts (``admin@rental.local``) outright.
    """

    email: str
    password: str


class ClientBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str


class UserOut(BaseModel):
    """The authenticated user. NEVER contains password_hash."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: str
    client_id: int | None = None
    client: ClientBrief | None = None
    is_active: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut
