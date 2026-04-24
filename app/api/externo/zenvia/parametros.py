from functools import lru_cache
from typing import Any
from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class ParametrosZenvia(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    api_base_url: AnyHttpUrl = Field(
        default="https://api.zenvia.com",
        validation_alias="ZENVIA_API_BASE_URL",
    )
    api_token: str | None = Field(default=None, validation_alias="ZENVIA_API_TOKEN")
    email_remetente_padrao: str | None = Field(
        default=None,
        validation_alias="ZENVIA_EMAIL_FROM",
    )
    sms_remetente_padrao: str | None = Field(
        default=None,
        validation_alias="ZENVIA_SMS_FROM",
    )

    @field_validator("api_token", mode="before")
    @classmethod
    def _vazio_como_none(cls, v: Any) -> Any:
        if v == "" or v is None:
            return None
        return v

    @field_validator("email_remetente_padrao", "sms_remetente_padrao", mode="before")
    @classmethod
    def _vazio_str_opcional(cls, v: Any) -> Any:
        if v == "":
            return None
        return v


@lru_cache
def obter_parametros_zenvia() -> ParametrosZenvia:
    return ParametrosZenvia()  
