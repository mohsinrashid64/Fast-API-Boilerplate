from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "My FastAPI App"
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    DEBUG: bool = True

    # Add all variables you have in .env
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GOOGLE_REDIRECT_URI: str | None = None
    SECRET_KEY: str | None = None
    ENCRYPTION_KEY: str | None = None
    DATABASE_URL: str = "sqlite:///./power.db"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
