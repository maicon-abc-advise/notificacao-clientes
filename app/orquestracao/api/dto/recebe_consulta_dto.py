from __future__ import annotations
import re
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field, field_validator


class RecebeConsultaCorpo(BaseModel):
    id_consulta: UUID
    cnpj_basico: str = Field(..., min_length=8, max_length=8)
    cnpj_ordem: str = Field(..., min_length=4, max_length=4)
    cnpj_dv: str = Field(..., min_length=2, max_length=2)
    email_fornecedor: EmailStr | None = None
    telefone_fornecedor: str | None = None
    motivo: str | None = Field(default=None, max_length=512)
    nome_fantasia: str | None = Field(default=None, max_length=256)

    @field_validator("email_fornecedor", "telefone_fornecedor", mode="before")
    @classmethod
    def _vazio_ou_omissao_para_none(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("cnpj_basico", "cnpj_ordem", "cnpj_dv")
    @classmethod
    def _so_digitos(cls, v: str) -> str:
        if not re.fullmatch(r"[0-9]+", v):
            raise ValueError("CNPJ: apenas dígitos")
        return v

    def cnpj_14(self) -> str:
        return f"{self.cnpj_basico}{self.cnpj_ordem}{self.cnpj_dv}"


class RespostaRecebeConsulta(BaseModel):
    acao: str = Field(description="email_enfileirado | sms_enfileirado | nada")
    id_consulta: UUID
    canal: str | None = None
    id_externo: str | None = None
    tipo_template: str | None = None
    motivo: str = ""
