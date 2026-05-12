from fastapi import APIRouter
from app.routes import auth, user, otp, product, role

# Combine all routers
router = APIRouter()

router.include_router(auth.router)
router.include_router(user.router)
router.include_router(otp.router)
router.include_router(product.router)
router.include_router(role.router)

