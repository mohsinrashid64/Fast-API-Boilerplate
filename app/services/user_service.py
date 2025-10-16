from http.client import HTTPException
from sqlalchemy.orm import Session

from app.models import User

from app.schemas.user import UserResponse
from typing import List
from app.utils.crypto_util import encrypt_data

class UserService:

    @staticmethod
    def get_current_user(db: Session, current_user: dict) -> UserResponse:
        user = db.query(User).filter(User.id == current_user["id"]).first()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Convert DB model to response schema
        return UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            phone_number=user.phone_number,
            is_verified=user.is_verified,
        )

    @staticmethod
    def get_all_users(db: Session) -> List[UserResponse]:
        users = db.query(User).all()
        return [UserResponse.model_validate(user) for user in users]
