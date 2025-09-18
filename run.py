import sys
import os

# Add project root (one level up from scripts/) to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))



import uvicorn
from app.core.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )
