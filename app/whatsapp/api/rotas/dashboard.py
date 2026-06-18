"""Rotas dashboard WhatsApp."""

from __future__ import annotations

import json
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.config.config import Configuracao, obter_configuracao
from app.dashboard.api.rotas_dashboard import (
    PAGE_SIZE,
    _append_param,
    _busca_cnpj,
    _meta,
    _page_clamped,
    _texto,
    registo_para_json,
)
from app.iam.rotas.dashboard_rotas import usuario_logado
from app.orquestracao.api.dependencias import PoolOrquestracao
from app.whatsapp.repositorios import postgres_whatsapp_envios as repo
from app.whatsapp.servicos.executar_envio_whatsapp import enviar_mensagem_inicial, validar_e_atualizar_numero
from app.whatsapp.servicos.rotina_whatsapp import (
    executar_atualizar_conversas_whatsapp,
    executar_envio_pendentes_whatsapp,
    executar_rotina_whatsapp,
)

router = APIRouter(
    prefix="/v1/interno/dashboard/whatsapp",
    tags=["dashboard — whatsapp"],
    dependencies=[Depends(usuario_logado)],
)


class CorpoEnviarWhatsapp(BaseModel):
    mensagem: str | None = Field(default=None, description="Texto customizado; omitir = template padrão")


class CorpoPatchStatus(BaseModel):
    status: str


class CorpoPatchFalhas(BaseModel):
    limpar: bool = Field(default=False, description="Se true, zera etapas de falha")


@router.get("/metricas")
async def metricas_whatsapp(pool: PoolOrquestracao) -> dict[str, Any]:
    por_status = await repo.contar_por_status(pool)
    por_wa = await repo.contar_whatsapp_status(pool)
    total = sum(por_status.values())
    return {
        "whatsapp_envios_total": total,
        "por_status": por_status,
        "por_whatsapp_status": por_wa,
        "cartoes": [
            {"chave": "pendente", "valor": por_status.get("pendente", 0), "legenda": "Pendentes"},
            {"chave": "contatado", "valor": por_status.get("contatado", 0), "legenda": "Contatados"},
            {"chave": "sucesso", "valor": por_status.get("concluido_sucesso", 0), "legenda": "Concluído sucesso"},
            {"chave": "falha", "valor": por_status.get("concluido_falha", 0), "legenda": "Concluído falha"},
        ],
        "barra_status": {
            "total_rotulo": "Envios",
            "total": total,
            "segmentos": [
                {
                    "chave": "pendente",
                    "rotulo": "Pendente",
                    "valor": por_status.get("pendente", 0),
                    "cor": "#94a3b8",
                    "filtro": {"aba": "postgres", "status": "pendente"},
                },
                {
                    "chave": "contatado",
                    "rotulo": "Contatado",
                    "valor": por_status.get("contatado", 0),
                    "cor": "#3b82f6",
                    "filtro": {"aba": "postgres", "status": "contatado"},
                },
                {
                    "chave": "sucesso",
                    "rotulo": "Sucesso",
                    "valor": por_status.get("concluido_sucesso", 0),
                    "cor": "#22c55e",
                    "filtro": {"aba": "postgres", "status": "concluido_sucesso"},
                },
                {
                    "chave": "falha",
                    "rotulo": "Falha",
                    "valor": por_status.get("concluido_falha", 0),
                    "cor": "#ef4444",
                    "filtro": {"aba": "postgres", "status": "concluido_falha"},
                },
            ],
        },
    }


@router.get("/postgres")
async def lista_whatsapp_postgres(
    pool: PoolOrquestracao,
    page: Annotated[int, Query(ge=1)] = 1,
    status: str | None = None,
    whatsapp_status: str | None = None,
    cnpj_basico: str | None = None,
) -> dict[str, Any]:
    page = _page_clamped(page)
    offset = (page - 1) * PAGE_SIZE
    status_f = _texto(status)
    wa_f = _texto(whatsapp_status)
    cnpj_f = _busca_cnpj(cnpj_basico)
    rows, total = await repo.listar_paginado(
        pool,
        offset=offset,
        limit=PAGE_SIZE,
        status=status_f,
        whatsapp_status=wa_f,
        cnpj_basico=cnpj_f,
    )
    itens = [registo_para_json(r) for r in rows]
    return {
        "origem": "postgres",
        "tabela_logica": "whatsapp_envios",
        "itens": itens,
        **_meta(total, page),
    }


@router.get("/contatos")
async def lista_whatsapp_contatos_legado(pool: PoolOrquestracao) -> dict[str, Any]:
    """Deprecated — redireciona conceitualmente para ``/postgres``."""
    return await lista_whatsapp_postgres(pool, page=1)


@router.get("/rotina/historico")
async def historico_rotina_whatsapp(
    pool: PoolOrquestracao,
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    rows = await repo.listar_execucoes_rotina(pool, limit=limit)
    return {"itens": [registo_para_json(r) for r in rows]}


@router.get("/rotina/execucao/{execucao_id}")
async def detalhe_execucao_rotina(pool: PoolOrquestracao, execucao_id: uuid.UUID) -> dict[str, Any]:
    row = await repo.buscar_execucao_rotina(pool, execucao_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execução não encontrada")
    d = registo_para_json(row)
    if isinstance(row["resultado"], (dict, list)):
        d["resultado"] = row["resultado"]
    elif row["resultado"]:
        d["resultado"] = json.loads(row["resultado"]) if isinstance(row["resultado"], str) else row["resultado"]
    return d


@router.post("/rotina/enviar-pendentes")
async def post_enviar_pendentes_dashboard(
    pool: PoolOrquestracao,
    config: Annotated[Configuracao, Depends(obter_configuracao)],
) -> dict[str, Any]:
    return (await executar_envio_pendentes_whatsapp(pool, config)).to_dict()


@router.post("/rotina/atualizar-conversas")
async def post_atualizar_conversas_dashboard(
    pool: PoolOrquestracao,
    config: Annotated[Configuracao, Depends(obter_configuracao)],
) -> dict[str, Any]:
    return (await executar_atualizar_conversas_whatsapp(pool, config)).to_dict()


@router.post("/rotina")
async def post_rotina_dashboard(
    pool: PoolOrquestracao,
    config: Annotated[Configuracao, Depends(obter_configuracao)],
) -> dict[str, Any]:
    """Wrapper completo (envio + conversas)."""
    return (await executar_rotina_whatsapp(pool, config)).to_dict()


@router.post("/{envio_id}/enviar")
async def post_enviar_whatsapp(
    envio_id: int,
    pool: PoolOrquestracao,
    config: Annotated[Configuracao, Depends(obter_configuracao)],
    corpo: CorpoEnviarWhatsapp | None = None,
) -> dict[str, Any]:
    try:
        return await enviar_mensagem_inicial(
            pool,
            config,
            envio_id,
            mensagem=corpo.mensagem if corpo else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.post("/{envio_id}/validar")
async def post_validar_whatsapp(
    envio_id: int,
    pool: PoolOrquestracao,
    config: Annotated[Configuracao, Depends(obter_configuracao)],
) -> dict[str, Any]:
    try:
        return await validar_e_atualizar_numero(pool, config, envio_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.patch("/{envio_id}/status")
async def patch_status_whatsapp(
    envio_id: int,
    corpo: CorpoPatchStatus,
    pool: PoolOrquestracao,
) -> dict[str, Any]:
    row = await repo.atualizar_status(pool, envio_id, status=corpo.status)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Envio não encontrado")
    return registo_para_json(row)


@router.patch("/{envio_id}/falhas")
async def patch_falhas_whatsapp(
    envio_id: int,
    corpo: CorpoPatchFalhas,
    pool: PoolOrquestracao,
) -> dict[str, Any]:
    if not corpo.limpar:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Use limpar=true")
    row = await pool.fetchrow(
        f"""
        UPDATE {repo._tabela()} SET etapa1 = NULL, etapa2 = NULL, etapa3 = NULL, updated_at = now()
        WHERE id = $1 RETURNING *
        """,
        envio_id,
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Envio não encontrado")
    return registo_para_json(row)


@router.get("/{envio_id}")
async def detalhe_whatsapp(pool: PoolOrquestracao, envio_id: int) -> dict[str, Any]:
    row = await repo.buscar_por_id(pool, envio_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Envio não encontrado")
    return registo_para_json(row)
