from __future__ import annotations

import re
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class RecebeConsultaCorpo(BaseModel):
    id_consulta: UUID
    cnpj_basico: str = Field(..., min_length=8, max_length=8)
    cnpj_ordem: str | None = None
    cnpj_dv: str | None = None
    email_fornecedor: EmailStr | None = None
    telefone_fornecedor: str | None = None
    nome_fantasia: str | None = Field(default=None, max_length=256)
    uf: str | None = Field(default=None, max_length=8)
    segmento: str | None = Field(default=None, max_length=256)

    @field_validator("email_fornecedor", "telefone_fornecedor", "uf", "segmento", mode="before")
    @classmethod
    def _vazio_ou_omissao_para_none(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("cnpj_ordem", "cnpj_dv", mode="before")
    @classmethod
    def _vazio_ordem_dv_para_none(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("uf", "segmento")
    @classmethod
    def _strip_opcionais(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        return s if s else None

    @field_validator("cnpj_basico")
    @classmethod
    def _so_digitos_basico(cls, v: str) -> str:
        if not re.fullmatch(r"[0-9]{8}", v):
            raise ValueError("cnpj_basico: exatamente 8 dígitos")
        return v

    @field_validator("cnpj_ordem")
    @classmethod
    def _so_digitos_ordem(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not re.fullmatch(r"[0-9]{4}", v):
            raise ValueError("cnpj_ordem: exatamente 4 dígitos")
        return v

    @field_validator("cnpj_dv")
    @classmethod
    def _so_digitos_dv(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not re.fullmatch(r"[0-9]{2}", v):
            raise ValueError("cnpj_dv: exatamente 2 dígitos")
        return v

    @model_validator(mode="after")
    def _ordem_e_dv_juntos(self) -> RecebeConsultaCorpo:
        o = self.cnpj_ordem
        d = self.cnpj_dv
        if (o is None) != (d is None):
            raise ValueError("Informe cnpj_ordem e cnpj_dv juntos ou omita ambos")
        return self

    def cnpj_14(self) -> str | None:
        """CNPJ de 14 dígitos quando ordem e DV vierem; senão ``None``."""
        if self.cnpj_ordem is None or self.cnpj_dv is None:
            return None
        return f"{self.cnpj_basico}{self.cnpj_ordem}{self.cnpj_dv}"


class RespostaRecebeConsulta(BaseModel):
    acao: str = Field(description="email_enfileirado | sms_enfileirado | nada")
    id_consulta: UUID
    canal: str | None = None
    id_externo: str | None = None
    tipo_template: str | None = None
    motivo: str = ""
