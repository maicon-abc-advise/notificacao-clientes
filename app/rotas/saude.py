"""Rota de verificação de disponibilidade (liveness)."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def verificar_saude() -> dict[str, str]:
    """Indica que o processo está no ar. Evoluir para readiness (ex.: Redis) depois."""
    return {"status": "ok"}
