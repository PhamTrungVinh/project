"""JWT authentication for services that do not own identity records."""

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

from shared_platform.auth_claims import AuthClaims
from utils.exceptions import UnauthorizedException
from utils.security import decode_access_token


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def get_current_claims(token: str = Depends(oauth2_scheme)) -> AuthClaims:
    payload = decode_access_token(token)
    if payload is None:
        raise UnauthorizedException()
    try:
        subject_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise UnauthorizedException()
    return AuthClaims(
        subject_id=subject_id,
        email=payload.get("email"),
        full_name=payload.get("name"),
    )
