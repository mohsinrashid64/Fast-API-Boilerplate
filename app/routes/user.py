from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas import UserResponse
from app.services import UserService
from app.utils import get_current_user

router = APIRouter()

# Route to get user details (requires token)
@router.get("/me", response_model=UserResponse)
def get_me(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    return UserService.get_current_user(db=db, current_user=current_user)

    
# Route to get all users (admin-only or privileged access)
@router.get("/users", response_model=List[UserResponse])
def get_all_users(db: Session = Depends(get_db)):
    return UserService.get_all_users(db=db)
