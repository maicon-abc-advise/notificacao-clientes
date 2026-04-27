from enum import StrEnum
from typing import Any
from pydantic import BaseModel, Field
from app.templates.modelo import CodigoTipoTemplate

class CanalMensagem(StrEnum):
    EMAIL = "email"
    SMS = "sms"

class PedidoEnvioEmail(BaseModel):
    destinatario: str = Field(..., min_length=3, description="E-mail do destinatário (campo to na API do provedor)")
    tipo_template: CodigoTipoTemplate = Field(
        ...,
        description="Código do registo em public.templates_notificacao.",
    )
    contexto: dict[str, str] = Field(
        default_factory=dict,
        description="Valores para substituir {{ chave }} no HTML do template.",
    )
    remetente: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description="ID do remetente (from); se omitido, usa ZENVIA_EMAIL_FROM no servidor.",
    )
    id_externo: str | None = Field(default=None, max_length=64, description="Mapeia para externalId se informado.")

class PedidoEnvioSms(BaseModel):
    destinatario: str = Field(
        ...,
        min_length=5,
        max_length=20,
        description="Destinatário no formato exigido pelo provedor (ex. E.164, sem espaços).",
    )
    tipo_template: CodigoTipoTemplate = Field(
        ...,
        description="Código do registo em public.templates_notificacao.",
    )
    contexto: dict[str, str] = Field(
        default_factory=dict,
        description="Valores para substituir {{ chave }} no texto SMS do template.",
    )
    remetente: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description="ID do remetente; se omitido, usa ZENVIA_SMS_FROM no servidor.",
    )
    id_externo: str | None = Field(default=None, max_length=64)

class PedidoEmailProvedor(BaseModel):
    destinatario: str = Field(..., min_length=3)
    assunto: str = Field(..., min_length=1)
    corpo_html: str = Field(..., min_length=1)
    remetente: str | None = Field(default=None, min_length=1, max_length=64)
    id_externo: str | None = Field(default=None, max_length=64)

class PedidoSmsProvedor(BaseModel):
    destinatario: str = Field(..., min_length=5, max_length=20)
    texto: str = Field(..., min_length=1)
    remetente: str | None = Field(default=None, min_length=1, max_length=64)
    id_externo: str | None = Field(default=None, max_length=64)

class ResultadoEnvioMensagem(BaseModel):
    id_provedor: str
    canal: CanalMensagem
    resposta_parcial: dict[str, Any] = Field(
        default_factory=dict,
        description="Trecho da resposta JSON (útil para suporte; pode vazio em testes).",
    )
