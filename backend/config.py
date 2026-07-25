from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    TOMTOM_API_KEY: str = "YOUR_TOMTOM_API_KEY"
    HERE_API_KEY: str = "YOUR_HERE_API_KEY"
    APP_ENV: str = "development"
    CACHE_TTL_SECONDS: int = 60  # cache traffic data for 60s

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()
