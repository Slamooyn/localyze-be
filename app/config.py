from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://localyze:localyze@localhost:5432/localyze"
    seed_mode: str = "synthetic"
    cors_origins: str = "http://localhost:3000"
    seed_version: str = "2026-07-01"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
