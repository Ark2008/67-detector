from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

# .env лежит в корне репозитория и общий с docker-compose.yml.
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "six_seven"
    postgres_user: str = "six_seven"
    postgres_password: str = "local_dev_password"

    cooldown_ms: int = Field(default=1500, ge=0)
    frame_window_size: int = Field(default=30, ge=1)
    # last_activity_at пишется в БД не на каждый кадр, а не чаще этого интервала.
    activity_touch_interval_seconds: float = Field(default=2.0, ge=0)

    session_timeout_seconds: float = Field(default=30.0, gt=0)
    timeout_check_interval_seconds: float = Field(default=5.0, gt=0)

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    @property
    def database_url(self) -> URL:
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


settings = Settings()
