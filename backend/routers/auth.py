"""Auth routes: the HTTP surface over the auth service.

One public endpoint for now — POST /auth/login. It is deliberately NOT protected
by get_current_user (you can't be logged in yet when you're logging in). The
get_current_user dependency that guards *other* routes lives in dependencies.py.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from config import Settings, get_settings
from database import get_db
from schemas.auth import LoginRequest, TokenResponse
from services.auth import create_access_token, verify_password
from services.user import get_user_by_email

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(
    data: LoginRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    # Same 401 whether the email is unknown or the password is wrong. Different
    # messages would let someone probe which emails are registered (user
    # enumeration). `or not verify_password` short-circuits, so we only hash-
    # compare when a user actually exists.
    user = get_user_by_email(db, data.email)
    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(user.id, settings)
    return TokenResponse(access_token=token)
