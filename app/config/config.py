from functools import lru_cache
from typing import Any, Self
from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from app.config.ambiente import Ambiente
from app.config.provedor_mensagens import ProvedorMensagem

def _strip(v: str | None) -> str:
    return (v or "").strip()

class Configuracao(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ambiente: Ambiente = Field(
        default=Ambiente.LOCAL,
        validation_alias="AMBIENTE",
        description="local | producao (também dev, prod, produção).",
    )

    mock_company_profile_enriquecimento: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "MOCK_COMPANY_PROFILE_ENRIQUECIMENTO",
            "USE_BIGDATACORP_MOCK",
        ),
        description="true = AdaptadorCompanyProfileMock; false = leitura Postgres em company_profile.",
    )
    use_zenvia_mock: bool = Field(
        default=True,
        validation_alias="USE_ZENVIA_MOCK",
        description="true = envio simulado sem chamar a API Zenvia.",
    )

    
    redis_url_test: str | None = Field(default=None, validation_alias="REDIS_URL_TEST")
    redis_url_prod: str | None = Field(default=None, validation_alias="REDIS_URL_PROD")
    redis_url_fallback: str | None = Field(default=None, validation_alias="REDIS_URL")
    redis_url: str = ""

    database_url_test: str | None = Field(default=None, validation_alias="DATABASE_URL_TEST")
    database_url_prod: str | None = Field(default=None, validation_alias="DATABASE_URL_PROD")
    database_url_fallback: str | None = Field(
        default="postgresql://notificacao:notificacao_dev@127.0.0.1:5433/notificacao",
        validation_alias="DATABASE_URL",
    )
    database_url: str = ""

    postgres_schema: str = Field(
        default="public",
        validation_alias="POSTGRES_SCHEMA",
        description="Schema Postgres das tabelas da API (ex.: public, busca_fornecedor).",
    )
    postgres_tabela_suffix: str = Field(
        default="",
        validation_alias="POSTGRES_TABELA_SUFFIX",
        description="Sufixo em consultas e usuario_fornecedor; FKs para usuario_fornecedor usam coluna fornecedor_id + sufixo (ex.: _teste).",
    )

    api_key: str = Field(validation_alias="API_KEY")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        validation_alias="CORS_ORIGINS",
        description="Origens CORS permitidas, separadas por vírgula (ex.: dashboard local e URL pública do front).",
    )

    zenvia_webhook_secret_prod: str | None = Field(default=None, validation_alias="ZENVIA_WEBHOOK_SECRET_PROD")
    zenvia_webhook_secret_fallback: str | None = Field(default=None, validation_alias="ZENVIA_WEBHOOK_SECRET")
    zenvia_webhook_secret: str | None = None

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

    limiar_creditos_no_fim: int = Field(
        default=5,
        ge=0,
        validation_alias="LIMIAR_CREDITOS_NO_FIM",
        description="Job verificar-creditos: aviso 'no fim' quando 0 < créditos <= limiar; zerados usam template de esgotados.",
    )
    link_area_creditos: str = Field(
        default="https://buscafornecedor.com.br/creditos",
        validation_alias="LINK_AREA_CREDITOS",
        description="URL nos e-mails de alerta de créditos (orquestração).",
    )

    mensagens_provedor_email: ProvedorMensagem = Field(
        default=ProvedorMensagem.ZENVIA,
        validation_alias="MENSAGENS_PROVEDOR_EMAIL",
    )
    mensagens_provedor_sms: ProvedorMensagem = Field(
        default=ProvedorMensagem.ZENVIA,
        validation_alias="MENSAGENS_PROVEDOR_SMS",
    )

    @field_validator("ambiente", mode="before")
    @classmethod
    def _normalizar_ambiente(cls, v: Any) -> Any:
        if isinstance(v, Ambiente):
            return v
        if isinstance(v, str):
            s = v.strip().lower()
            if s in ("local", "dev", "development"):
                return Ambiente.LOCAL
            if s in ("producao", "prod", "production", "produção"):
                return Ambiente.PRODUCAO
        return v

    @field_validator(
        "mock_company_profile_enriquecimento",
        "use_zenvia_mock",
        mode="before",
    )
    @classmethod
    def _bool_flags(cls, v: Any) -> Any:
        if isinstance(v, str):
            s = v.strip().lower()
            if s in ("1", "true", "yes", "on"):
                return True
            if s in ("0", "false", "no", "off", ""):
                return False
        return v

    @field_validator("zenvia_webhook_secret_fallback", "zenvia_webhook_secret_prod", mode="before")
    @classmethod
    def _webhook_secret_vazio_none(cls, v: Any) -> Any:
        if v == "" or v is None:
            return None
        return v

    @field_validator("postgres_schema", mode="before")
    @classmethod
    def _postgres_schema_strip(cls, v: Any) -> Any:
        if v is None:
            return "public"
        if isinstance(v, str):
            s = v.strip()
            return s if s else "public"
        return v

    @field_validator("postgres_tabela_suffix", mode="before")
    @classmethod
    def _postgres_suffix_strip(cls, v: Any) -> Any:
        if v is None:
            return ""
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("mensagens_provedor_email", "mensagens_provedor_sms", mode="before")
    @classmethod
    def _normalizar_provedor(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip().lower()
        return v

    @model_validator(mode="after")
    def _aplicar_redis_postgres(self) -> Self:
        local = self.ambiente == Ambiente.LOCAL

        r_test, r_prod, r_fb = _strip(self.redis_url_test), _strip(self.redis_url_prod), _strip(self.redis_url_fallback)
        pick_redis = (r_test if local else r_prod) or r_fb
        if not pick_redis:
            raise ValueError(
                "Defina REDIS_URL_TEST (AMBIENTE=local) ou REDIS_URL_PROD (AMBIENTE=producao), "
                "ou REDIS_URL como retorno.",
            )
        object.__setattr__(self, "redis_url", pick_redis)

        d_test, d_prod = _strip(self.database_url_test), _strip(self.database_url_prod)
        d_fb = _strip(self.database_url_fallback)
        pick_db = (d_test if local else d_prod) or d_fb
        if not pick_db:
            raise ValueError(
                "Defina DATABASE_URL_TEST ou DATABASE_URL_PROD conforme AMBIENTE, ou DATABASE_URL como retorno.",
            )
        object.__setattr__(self, "database_url", pick_db)

        wh = _strip(self.zenvia_webhook_secret_prod) or self.zenvia_webhook_secret_fallback
        object.__setattr__(self, "zenvia_webhook_secret", wh)

        return self

    def listar_origens_cors(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def obter_configuracao() -> Configuracao:
    return Configuracao()
