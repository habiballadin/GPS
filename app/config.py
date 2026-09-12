from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./gps.db"
    jwt_secret: str = "change-me"
    jwt_expire_minutes: int = 60 * 24
    tcp_teltonika_host: str = "0.0.0.0"
    tcp_teltonika_port: int = 5001
    tcp_gt06_host: str = "0.0.0.0"
    tcp_gt06_port: int = 5002
    max_packet_bytes: int = 8192
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
