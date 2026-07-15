from __future__ import annotations
from fastapi import APIRouter, Depends
from app.iam.dependencias import verificar_chamada_interna
from app.orquestracao.api.rotas import (
    codigo_verificacao_router,
    comprador_busca_router,
    emails_pendentes_router,
    fornecedor_contato_router,
    recebe_consulta_router,
    sincronizar_conversoes_compradores_router,
    verificar_creditos_router,
)

router = APIRouter(
    prefix="/v1/interno/orquestracao",
    tags=["orquestracao"],
    dependencies=[Depends(verificar_chamada_interna)],
)

router.include_router(recebe_consulta_router)
router.include_router(verificar_creditos_router)
router.include_router(emails_pendentes_router)
router.include_router(codigo_verificacao_router)
router.include_router(comprador_busca_router)
router.include_router(fornecedor_contato_router)
router.include_router(sincronizar_conversoes_compradores_router)
