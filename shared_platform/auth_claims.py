from pydantic import BaseModel


class AuthClaims(BaseModel):
    """Minimal, trusted identity propagated to internal services."""

    subject_id: int
    email: str | None = None
    full_name: str | None = None

    @property
    def id(self) -> int:
        """Compatibility with chat code that reads the authenticated owner's ID."""
        return self.subject_id
