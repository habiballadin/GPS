from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./gps.db"
    jwt_secret: str = "change-me"
    jwt_expire_minutes: int = 60 * 24
    refresh_expire_days: int = 30
    app_base_url: str = "http://localhost:3000"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "no-reply@gps-fleet.local"
    smtp_starttls: bool = True
    currency_code: str = "INR"
    currency_symbol: str = "₹"
    locale: str = "en-IN"
    timezone: str = "Asia/Kolkata"
    audit_retention_days: int = 365
    tcp_teltonika_host: str = "0.0.0.0"
    tcp_teltonika_port: int = 5001
    tcp_gt06_host: str = "0.0.0.0"
    tcp_gt06_port: int = 5002
    max_packet_bytes: int = 8192
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
