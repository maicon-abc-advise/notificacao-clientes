from fastapi import APIRouter, Depends
from app.nucleo.dependencias import verificar_chamada_interna

router = APIRouter(prefix="/v1", dependencies=[Depends(verificar_chamada_interna)])

@router.get("/ping-autenticado")
def get_ping_autenticado() -> dict[str, bool]:
    return {"autenticado": True}
