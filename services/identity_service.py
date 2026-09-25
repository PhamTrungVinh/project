from identity_service.models import User
from shared_platform.auth_claims import AuthClaims

def claims_for_user(user: User) -> AuthClaims:
    return AuthClaims(subject_id=user.id, email=user.email, full_name=user.full_name)


def contact_for_owner(db, owner_id: int) -> tuple[str | None, str | None]:
    """Return the canonical contact details for an authenticated account."""
    user = db.get(User, owner_id)
    if user is None:
        return None, None
    return user.full_name, user.email
