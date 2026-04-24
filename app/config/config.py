from functools import lru_cache
from typing import Any
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from app.config.provedor_mensagens import ProvedorMensagem


class Configuracao(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    api_key: str = Field(validation_alias="API_KEY")
    redis_url: str = Field(validation_alias="REDIS_URL")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    # provedor de email
    mensagens_provedor_email: ProvedorMensagem = Field(
        default=ProvedorMensagem.ZENVIA,
        validation_alias="MENSAGENS_PROVEDOR_EMAIL",
    )

    # provedor de sms
    mensagens_provedor_sms: ProvedorMensagem = Field(
        default=ProvedorMensagem.ZENVIA,
        validation_alias="MENSAGENS_PROVEDOR_SMS",
    )

    @field_validator("mensagens_provedor_email", "mensagens_provedor_sms", mode="before")
    @classmethod
    def _normalizar_provedor(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip().lower()
        return v


@lru_cache
def obter_configuracao() -> Configuracao:
    return Configuracao() 
