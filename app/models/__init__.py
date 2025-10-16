from .user import User
from .user_auth import UserAuth
from .otp import OTP
from .reset_token import ResetToken
from .product import Product

# Add more models here later
# from .otp import Otp
# from .reset_token import ResetToken

# Optional: Export a list of all models (useful for migrations)
__all__ = ["User", "UserAuth", "Otp", "ResetToken"]
