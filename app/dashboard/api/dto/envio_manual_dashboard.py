from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.dashboard.api.dto.mutacoes_dashboard import CorpoConfirmacaoSenha
from app.templates.modelo import CodigoTipoTemplate


class CorpoCriarPendenteDashboard(BaseModel):
    cnpj_basico: str = Field(..., min_length=8, max_length=8)
    destinatario: str = Field(..., min_length=3)
    tipo_template: CodigoTipoTemplate
    nome_fantasia: str | None = Field(default=None, max_length=256)
    uf: str | None = Field(default=None, max_length=32)
    segmento: str | None = Field(default=None, max_length=256)
    fornecedor_id: UUID | None = None
    cnpj: str | None = Field(default=None, max_length=18, description="CNPJ completo opcional (14 dígitos)")


class CorpoEnviarPendenteDashboard(CorpoConfirmacaoSenha):
    pass
