from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class TipoVariavelSistema(StrEnum):
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    STRING = "string"
    PERCENT = "percent"


class OrigemVariavelSistema(StrEnum):
    BANCO = "banco"
    ENV = "env"


class VariavelSistemaRegistro(BaseModel):
    chave: str
    valor: str
    tipo: TipoVariavelSistema
    grupo: str
    descricao: str = ""
    editavel: bool = True


class VariavelSistemaItem(BaseModel):
    chave: str
    valor: str
    tipo: TipoVariavelSistema
    grupo: str
    descricao: str = ""
    editavel: bool = True
    origem: OrigemVariavelSistema
    valor_efetivo: str


class GrupoVariaveisSistema(BaseModel):
    nome: str
    rotulo: str
    variaveis: list[VariavelSistemaItem] = Field(default_factory=list)


class RespostaListagemVariaveis(BaseModel):
    grupos: list[GrupoVariaveisSistema]


class CorpoAtualizarVariavel(BaseModel):
    valor: str = Field(..., min_length=0, max_length=4096)
