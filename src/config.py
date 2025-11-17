"""Application configuration using Pydantic settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database settings
    database_url: str = "sqlite+aiosqlite:///./data/database.db"

    # MQTT settings
    mqtt_broker_host: str = "localhost"
    mqtt_broker_port: int = 1883
    mqtt_topic: str = "isic/scan"
    mqtt_client_id: str = "isic-backend"

    # Application settings
    app_name: str = "ISIC Backend"
    app_version: str = "0.1.0"
    debug: bool = False


settings = Settings()

