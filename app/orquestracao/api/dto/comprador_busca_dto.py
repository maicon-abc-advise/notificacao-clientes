from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.orquestracao.servicos.comprador_busca_constantes import CanalCompradorBusca


class PedidoSmsCompradorBusca(BaseModel):
    consulta_id: UUID
    comprador_id: UUID
    telefone: str = Field(..., min_length=5, max_length=500)
    url: str = Field(..., min_length=1, max_length=2048)
    primeira_consulta_sem_cadastro: bool


class RespostaSmsCompradorBusca(BaseModel):
    id_externo: str
    id_provedor: str
    status_ultimo: str = "processando"
    idempotente: bool = False


class PedidoEnviarCompradorBusca(BaseModel):
    consulta_id: UUID
    comprador_id: UUID
    telefone: str = Field(..., min_length=5, max_length=500)
    url: str = Field(..., min_length=1, max_length=2048)
    primeira_consulta_sem_cadastro: bool
    canal: CanalCompradorBusca | None = Field(
        default=None,
        description="Canal de envio. Omitido: backend resolve via configuração (hoje: sms).",
    )


class RespostaEnviarCompradorBusca(BaseModel):
    canal: CanalCompradorBusca
    id_externo: str
    id_provedor: str
    status_ultimo: str = "processando"
    idempotente: bool = False
