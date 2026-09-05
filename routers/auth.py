from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from database import get_db
from schemas.user import UserCreate, UserOut, Token
from crud.users import get_user_by_email, create_user
from utils.security import verify_password, create_access_token
from utils.exceptions import ConflictException, UnauthorizedException
from logger import app_logger

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut)
def register(user: UserCreate, db: Session = Depends(get_db)):
    if get_user_by_email(db, user.email):
        app_logger.warning("registration_rejected duplicate_email")
        raise ConflictException("Email already registered")
    created_user = create_user(db, user)
    app_logger.info("registration_succeeded user_id=%s", created_user.id)
    return created_user


@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # OAuth2PasswordRequestForm uses the OAuth2-standard "username" field,
    # but this application authenticates by email, so email is supplied as username.
    user = get_user_by_email(db, form_data.username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        app_logger.warning("login_rejected invalid_credentials")
        raise UnauthorizedException("Incorrect email or password")

    access_token = create_access_token(data={"sub": str(user.id)})
    app_logger.info("login_succeeded user_id=%s", user.id)
    return Token(access_token=access_token)