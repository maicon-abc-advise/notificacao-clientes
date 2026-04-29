from functools import lru_cache
from typing import Any, Self

from pydantic import AnyHttpUrl, Field, TypeAdapter, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _strip(v: str | None) -> str:
    return (v or "").strip()


class ParametrosZenvia(BaseSettings):
    """Credenciais Zenvia de produção (sem sufixo _TEST). Opcionalmente use *_PROD ou variáveis sem sufixo."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    zenvia_api_base_url_prod: str | None = Field(default=None, validation_alias="ZENVIA_API_BASE_URL_PROD")
    zenvia_api_base_url_fallback: str = Field(
        default="https://api.zenvia.com",
        validation_alias="ZENVIA_API_BASE_URL",
    )

    zenvia_api_token_prod: str | None = Field(default=None, validation_alias="ZENVIA_API_TOKEN_PROD")
    zenvia_api_token_fallback: str | None = Field(default=None, validation_alias="ZENVIA_API_TOKEN")

    zenvia_email_from_prod: str | None = Field(default=None, validation_alias="ZENVIA_EMAIL_FROM_PROD")
    zenvia_email_from_fallback: str | None = Field(default=None, validation_alias="ZENVIA_EMAIL_FROM")

    zenvia_sms_from_prod: str | None = Field(default=None, validation_alias="ZENVIA_SMS_FROM_PROD")
    zenvia_sms_from_fallback: str | None = Field(default=None, validation_alias="ZENVIA_SMS_FROM")

    api_base_url: AnyHttpUrl = Field(default="https://api.zenvia.com")
    api_token: str | None = None
    email_remetente_padrao: str | None = None
    sms_remetente_padrao: str | None = None

    @field_validator("zenvia_api_token_fallback", mode="before")
    @classmethod
    def _vazio_token_fb(cls, v: Any) -> Any:
        if v == "" or v is None:
            return None
        return v

    @field_validator("zenvia_email_from_fallback", "zenvia_sms_from_fallback", mode="before")
    @classmethod
    def _vazio_str_fb(cls, v: Any) -> Any:
        if v == "":
            return None
        return v

    @field_validator(
        "zenvia_api_token_prod",
        "zenvia_api_base_url_prod",
        "zenvia_email_from_prod",
        "zenvia_sms_from_prod",
        mode="before",
    )
    @classmethod
    def _vazio_opcionais_prod(cls, v: Any) -> Any:
        if v == "" or v is None:
            return None
        return v

    @model_validator(mode="after")
    def _merge_credenciais(self) -> Self:
        base_pick = _strip(self.zenvia_api_base_url_prod) or _strip(self.zenvia_api_base_url_fallback) or "https://api.zenvia.com"
        ta = TypeAdapter(AnyHttpUrl)
        object.__setattr__(self, "api_base_url", ta.validate_python(base_pick))

        tok = _strip(self.zenvia_api_token_prod) or _strip(self.zenvia_api_token_fallback) or None
        object.__setattr__(self, "api_token", tok)

        em = _strip(self.zenvia_email_from_prod) or _strip(self.zenvia_email_from_fallback) or None
        object.__setattr__(self, "email_remetente_padrao", em)

        sm = _strip(self.zenvia_sms_from_prod) or _strip(self.zenvia_sms_from_fallback) or None
        object.__setattr__(self, "sms_remetente_padrao", sm)

        return self


@lru_cache
def obter_parametros_zenvia() -> ParametrosZenvia:
    return ParametrosZenvia()
