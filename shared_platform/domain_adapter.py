"""Common identity forwarding for optional HTTP domain adapters."""

from models.user import User
from shared_platform.auth_claims import AuthClaims
from utils.security import create_access_token


def token_for_claims(claims: AuthClaims) -> str:
    return create_access_token(
        {
            "sub": str(claims.subject_id),
            "email": claims.email,
            "name": claims.full_name,
        }
    )


def token_for_user(user: User) -> str:
    return token_for_claims(AuthClaims(subject_id=user.id, email=user.email, full_name=user.full_name))
