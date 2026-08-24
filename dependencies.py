from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from database import get_db
from utils.security import decode_access_token
from utils.exceptions import UnauthorizedException
from crud.users import get_user_by_id
from models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    payload = decode_access_token(token)
    if payload is None:
        raise UnauthorizedException()

    user_id_raw = payload.get("sub")
    if user_id_raw is None:
        raise UnauthorizedException()

    try:
        user_id = int(user_id_raw)
    except (TypeError, ValueError):
        raise UnauthorizedException()

    user = get_user_by_id(db, user_id)
    if user is None:
        raise UnauthorizedException()

    return user