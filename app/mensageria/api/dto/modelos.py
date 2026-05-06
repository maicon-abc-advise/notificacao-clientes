from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from app.templates.modelo import CodigoTipoTemplate

class CanalMensagem(StrEnum):
    EMAIL = "email"
    SMS = "sms"

class PedidoEnvioEmail(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
        description="Ignorado no envio: o remetente vem só de ZENVIA_EMAIL_FROM / configuração do servidor.",
    )
    id_externo: str | None = Field(
        default=None,
        max_length=64,
        description="Correlação do envio; na API Zenvia é enviado como externalId.",
    )
    fornecedor_id: UUID | None = Field(
        default=None,
        description="Opcional: atualiza engajamento_fornecedores em eventos de e-mail (API + webhooks).",
    )
    cnpj_basico: str | None = Field(
        default=None,
        min_length=8,
        max_length=8,
        description="Opcional: identificador principal de engajamento quando não houver fornecedor_id.",
    )
    consulta_id: UUID | None = Field(
        default=None,
        description="Opcional: trava deduplicação na orquestração (recebe-consulta); repassado às filas Redis.",
    )

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
        description="Ignorado no envio: o remetente vem só de ZENVIA_SMS_FROM / configuração do servidor.",
    )
    id_externo: str | None = Field(default=None, max_length=64)
    fornecedor_id: UUID | None = Field(
        default=None,
        description="Opcional: liga o envio a engajamento_fornecedores e webhooks de estado.",
    )
    cnpj_basico: str | None = Field(
        default=None,
        min_length=8,
        max_length=8,
        description="Opcional: identificador principal de engajamento quando não houver fornecedor_id.",
    )
    consulta_id: UUID | None = Field(
        default=None,
        description="Opcional: trava deduplicação na orquestração; repassado à fila Redis.",
    )

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
