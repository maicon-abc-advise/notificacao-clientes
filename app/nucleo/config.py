from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Configuracao(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    api_key: str = Field(validation_alias="API_KEY")
    redis_url: str = Field(validation_alias="REDIS_URL")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

@lru_cache
def obter_configuracao() -> Configuracao:
    return Configuracao()  
