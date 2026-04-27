from typing import Protocol, runtime_checkable
from app.templates.modelo import TemplateNotificacao

@runtime_checkable
class PortaTemplates(Protocol):
    async def obter_por_tipo(self, codigo: str) -> TemplateNotificacao | None: ...
    async def listar_todos(self) -> list[TemplateNotificacao]: ...
