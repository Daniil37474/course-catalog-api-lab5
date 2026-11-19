from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    database_url: str
    secret_key: str = Field(min_length=32)
    access_token_minutes: int = Field(default=15, ge=1, le=60)
    sql_echo: bool = False
    graphql_introspection: bool = True


settings = Settings()
