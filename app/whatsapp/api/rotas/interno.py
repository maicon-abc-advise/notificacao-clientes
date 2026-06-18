"""Rotas internas WhatsApp (cron / n8n)."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.config.config import Configuracao, obter_configuracao
from app.iam.dependencias import verificar_chamada_interna
from app.orquestracao.api.dependencias import PoolOrquestracao
from app.whatsapp.repositorios import postgres_whatsapp_envios as repo
from app.whatsapp.servicos.rotina_whatsapp import (
    executar_atualizar_conversas_whatsapp,
    executar_envio_pendentes_whatsapp,
    executar_rotina_whatsapp,
)

router = APIRouter(
    prefix="/v1/interno/whatsapp",
    tags=["interno — whatsapp"],
    dependencies=[Depends(verificar_chamada_interna)],
)


@router.post("/enviar-pendentes")
async def post_enviar_pendentes_whatsapp(
    pool: PoolOrquestracao,
    config: Annotated[Configuracao, Depends(obter_configuracao)],
) -> dict[str, Any]:
    """Valida número e envia mensagem inicial para fila ``pendente``."""
    return (await executar_envio_pendentes_whatsapp(pool, config)).to_dict()


@router.post("/enviar-pendentes/{envio_id}")
async def post_enviar_pendentes_whatsapp_um(
    envio_id: int,
    pool: PoolOrquestracao,
    config: Annotated[Configuracao, Depends(obter_configuracao)],
) -> dict[str, Any]:
    row = await repo.buscar_por_id(pool, envio_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Envio não encontrado")
    if str(row["status"]) != "pendente":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Envio não está pendente")
    return (await executar_envio_pendentes_whatsapp(pool, config, envio_id=str(envio_id))).to_dict()


@router.post("/atualizar-conversas")
async def post_atualizar_conversas_whatsapp(
    pool: PoolOrquestracao,
    config: Annotated[Configuracao, Depends(obter_configuracao)],
) -> dict[str, Any]:
    """Lê chat e atualiza funil para registros ``contatado``."""
    return (await executar_atualizar_conversas_whatsapp(pool, config)).to_dict()


@router.post("/atualizar-conversas/{envio_id}")
async def post_atualizar_conversas_whatsapp_um(
    envio_id: int,
    pool: PoolOrquestracao,
    config: Annotated[Configuracao, Depends(obter_configuracao)],
) -> dict[str, Any]:
    row = await repo.buscar_por_id(pool, envio_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Envio não encontrado")
    if str(row["status"]) != "contatado":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Envio não está contatado")
    return (await executar_atualizar_conversas_whatsapp(pool, config, envio_id=str(envio_id))).to_dict()


@router.post("/rotina")
async def post_rotina_whatsapp(
    pool: PoolOrquestracao,
    config: Annotated[Configuracao, Depends(obter_configuracao)],
) -> dict[str, Any]:
    """Wrapper: enviar-pendentes + atualizar-conversas (compatibilidade)."""
    return (await executar_rotina_whatsapp(pool, config)).to_dict()


@router.post("/rotina/{envio_id}")
async def post_rotina_whatsapp_um(
    envio_id: int,
    pool: PoolOrquestracao,
    config: Annotated[Configuracao, Depends(obter_configuracao)],
) -> dict[str, Any]:
    row = await repo.buscar_por_id(pool, envio_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Envio não encontrado")
    return (await executar_rotina_whatsapp(pool, config, envio_id=str(envio_id))).to_dict()
