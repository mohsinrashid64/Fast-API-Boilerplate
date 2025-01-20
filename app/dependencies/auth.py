from fastapi import Depends, Request, HTTPException
from sqlalchemy.orm import Session
from app.database.db_config import get_db
from app.models.user import User

def get_current_user(request: Request, db: Session = Depends(get_db)):
    """
    Retrieve the current user from the database using JWT payload.
    """
    user_payload = request.state.user
    if not user_payload:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    user = db.query(User).filter(User.id == user_payload["sub"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
