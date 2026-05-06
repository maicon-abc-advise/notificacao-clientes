from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class ResultadoEnriquecimentoContato:
    email: str | None
    telefone: str | None
    emails: tuple[str, ...] = field(default_factory=tuple)
    telefones: tuple[str, ...] = field(default_factory=tuple)


@runtime_checkable
class PortaEnriquecimentoContato(Protocol):
    async def enriquecer_por_cnpj_basico(self, cnpj_basico: str) -> ResultadoEnriquecimentoContato: ...
