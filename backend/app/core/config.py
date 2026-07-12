from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "apartment103-backend"
    environment: str = "local"

    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "apartment103"


settings = Settings()
