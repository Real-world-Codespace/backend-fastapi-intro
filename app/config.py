import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///./task_manager.db"
    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"
    ai_mode: str = "openai"
    cookie_secure: bool = False
    ai_max_requests_per_hour: int = 30


def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL", "sqlite:///./task_manager.db"),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
        ai_mode=os.getenv("AI_MODE", "openai"),
        cookie_secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        ai_max_requests_per_hour=int(os.getenv("AI_MAX_REQUESTS_PER_HOUR", "30")),
    )
