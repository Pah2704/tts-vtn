from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PIPER_BIN: str = "piper"
    PIPER_MODEL_PATH: str
    PIPER_CONFIG_PATH: str | None = None
    PIPER_TIMEOUT_SEC: int = 60  # tránh treo subprocess

    class Config:
        env_file = "backend/.env"
        env_file_encoding = "utf-8"

settings = Settings()
