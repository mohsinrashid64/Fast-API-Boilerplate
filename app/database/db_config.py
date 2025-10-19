import os
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Use async SQLite by default
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./power.db")

# ✅ Create async engine (aiosqlite supports async I/O)
engine = create_async_engine(DATABASE_URL, echo=True, future=True)

# ✅ Create async session
AsyncSessionLocal = sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)

# ✅ Declarative Base
Base = declarative_base()

# ✅ Dependency for FastAPI routes
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

# ✅ Async function to create tables
async def create_database():
    print('Creating database tables...')
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# ✅ Optional: for manual creation
if __name__ == "__main__":
    asyncio.run(create_database())
