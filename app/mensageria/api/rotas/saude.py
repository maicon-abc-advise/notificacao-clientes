from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
def verificar_saude() -> dict[str, str]:
    return {"status": "ok"}
