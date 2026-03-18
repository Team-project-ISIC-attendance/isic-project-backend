from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    database_url: str = "sqlite+aiosqlite:///./data/database.db"

    mqtt_broker_host: str = "localhost"
    mqtt_broker_port: int = 1883
    mqtt_topic: str = "isic/scan"
    mqtt_client_id: str = "isic-backend"

    app_name: str = "ISIC Backend"
    app_version: str = "0.1.0"
    debug: bool = False

    http_host: str
    http_port: int

    jwt_secret_key: str
    jwt_expiry_hours: int = 24
    cors_origins: str = "*"
    admin_email: str = "admin@stuba.sk"
    admin_password: str = "admin"

    scan_window_before_minutes: int = 15
    scan_window_after_minutes: int = 5


settings = Settings()

