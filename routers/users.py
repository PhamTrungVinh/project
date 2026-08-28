from fastapi import APIRouter, Depends

from dependencies import get_current_user
from models.user import User
from schemas.user import UserOut

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user