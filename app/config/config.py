from functools import lru_cache
from typing import Any
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from app.config.provedor_mensagens import ProvedorMensagem


class Configuracao(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    api_key: str = Field(validation_alias="API_KEY")
    redis_url: str = Field(validation_alias="REDIS_URL")
    database_url: str = Field(
        default="postgresql://notificacao:notificacao_dev@127.0.0.1:5433/notificacao",
        validation_alias="DATABASE_URL",
    )
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    # webhooks Zenvia (reenvio): se vazio, rotas de webhook não exigem X-Webhook-Secret (só para dev local).
    zenvia_webhook_secret: str | None = Field(default=None, validation_alias="ZENVIA_WEBHOOK_SECRET")
    sweep_emails_esperando_confirmacao_dias: int = Field(
        default=2,
        ge=1,
        le=365,
        validation_alias=AliasChoices(
            "SWEEP_EMAILS_ESPERANDO_CONFIRMACAO_DIAS",
            "SWEEP_EMAIL_PENDENTE_DIAS",
        ),
    )
    reenvio_sms_reprocessar_max: int = Field(default=10, ge=0, le=1000, validation_alias="REENVIO_SMS_REPROCESSAR_MAX")

    use_bigdatacorp_mock: bool = Field(
        default=True,
        validation_alias="USE_BIGDATACORP_MOCK",
        description="Se true, enriquecimento usa AdaptadorBigDataCorpMock; se false, adaptador API (ainda não implementado).",
    )

    # Rotas /v1/interno/teste-pipeline/* — só ativas se true (não usar em produção pública).
    teste_pipeline_habilitado: bool = Field(
        default=False,
        validation_alias="TESTE_PIPELINE_HABILITADO",
    )

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

    @field_validator("teste_pipeline_habilitado", "use_bigdatacorp_mock", mode="before")
    @classmethod
    def _bool_flags(cls, v: Any) -> Any:
        if isinstance(v, str):
            s = v.strip().lower()
            if s in ("1", "true", "yes", "on"):
                return True
            if s in ("0", "false", "no", "off", ""):
                return False
        return v

    @field_validator("zenvia_webhook_secret", mode="before")
    @classmethod
    def _webhook_secret_vazio_none(cls, v: Any) -> Any:
        if v == "" or v is None:
            return None
        return v

    @field_validator("mensagens_provedor_email", "mensagens_provedor_sms", mode="before")
    @classmethod
    def _normalizar_provedor(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip().lower()
        return v


@lru_cache
def obter_configuracao() -> Configuracao:
    return Configuracao()
