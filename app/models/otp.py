from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database.db_config import Base
from app.utils.time import utcnow


class OTP(Base):
    __tablename__ = "otps"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    otp_code = Column(String(10), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=utcnow)
    verified = Column(Boolean, default=False)

    user = relationship("User", back_populates="otps")

    def __str__(self) -> str:
        return f"OTP #{self.id} (user #{self.user_id})"
