"""Pydantic schemas for the auth endpoints.

    LoginRequest  — the POST /auth/login body: email + password.
    TokenResponse — the response: a signed JWT the client stores and sends back
                    on later requests as `Authorization: Bearer <token>`.

Email is a plain str, not Pydantic's EmailStr: there is no public signup (only
me, seeded by hand), so strict format validation would pull in an extra
dependency to guard input that only I ever type. Revisit if signup is ever built.
"""

from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    # token_type is a convention clients expect; "bearer" tells them to send the
    # token as `Authorization: Bearer <token>`.
    token_type: str = "bearer"
