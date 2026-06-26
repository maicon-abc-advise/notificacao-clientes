"""Rotas dashboard WhatsApp."""

from __future__ import annotations

import json
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from uuid import UUID

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
from app.whatsapp.servicos.entrada_whatsapp_apos_falha_email import entrada_whatsapp_apos_falha_email
from app.whatsapp.servicos.executar_envio_whatsapp import enviar_mensagem_inicial, validar_e_atualizar_numero
from app.whatsapp.servicos.telefone_whatsapp import normalizar_telefone_whatsapp
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


class CorpoCriarWhatsappPendenteDashboard(BaseModel):
    cnpj_basico: str = Field(..., min_length=8, max_length=8)
    telefone: str = Field(..., min_length=8)
    fornecedor_id: UUID | None = None


_MENSAGENS_CRIAR_WHATSAPP: dict[str, tuple[int, str]] = {
    "whatsapp_inserido": (status.HTTP_201_CREATED, "Inserido na fila WhatsApp"),
    "whatsapp_ja_na_fila": (status.HTTP_409_CONFLICT, "CNPJ ou telefone já está na fila"),
    "whatsapp_ignorado_cadastrado": (status.HTTP_409_CONFLICT, "Fornecedor já cadastrou na plataforma"),
    "whatsapp_ignorado_falha": (
        status.HTTP_409_CONFLICT,
        "Aguardando novas buscas antes de reabrir WhatsApp",
    ),
    "whatsapp_sem_telefone": (status.HTTP_400_BAD_REQUEST, "Telefone inválido ou ausente"),
}


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


@router.post("/postgres", status_code=status.HTTP_201_CREATED)
async def post_criar_whatsapp_pendente(
    pool: PoolOrquestracao,
    config: Annotated[Configuracao, Depends(obter_configuracao)],
    body: CorpoCriarWhatsappPendenteDashboard,
) -> dict[str, Any]:
    """Inserção manual na fila ``whatsapp_envios`` (status ``pendente``)."""
    cnpj = body.cnpj_basico.strip()
    try:
        tel = normalizar_telefone_whatsapp(body.telefone)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    resultado = await entrada_whatsapp_apos_falha_email(
        pool,
        config,
        cnpj_basico=cnpj,
        fornecedor_id=body.fornecedor_id,
        origem="dashboard_manual",
        telefone=tel,
    )
    retorno = str(resultado.get("retorno") or "")
    if retorno != "whatsapp_inserido":
        codigo, msg = _MENSAGENS_CRIAR_WHATSAPP.get(
            retorno,
            (status.HTTP_400_BAD_REQUEST, retorno or "Não foi possível inserir na fila"),
        )
        raise HTTPException(status_code=codigo, detail=msg)

    envio_id = resultado.get("id")
    row = await repo.buscar_por_id(pool, envio_id) if envio_id else None
    if row is None:
        row = await repo.buscar_por_cnpj_telefone(pool, cnpj_basico=cnpj, numero_telefone=tel)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Inserido, mas registro não encontrado",
        )
    return {
        "origem": "postgres",
        "tabela_logica": "whatsapp_envios",
        "item": registo_para_json(row),
        "retorno": retorno,
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
    limite: Annotated[int | None, Query(ge=1, le=200)] = None,
) -> dict[str, Any]:
    return (await executar_envio_pendentes_whatsapp(pool, config, limite=limite)).to_dict()


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
    limite: Annotated[int | None, Query(ge=1, le=200)] = None,
) -> dict[str, Any]:
    """Wrapper completo (envio + conversas). ``limite`` aplica-se só ao envio."""
    return (await executar_rotina_whatsapp(pool, config, limite_envio=limite)).to_dict()


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


@router.post("/{envio_id}/atualizar-conversa")
async def post_atualizar_conversa_whatsapp(
    envio_id: int,
    pool: PoolOrquestracao,
    config: Annotated[Configuracao, Depends(obter_configuracao)],
) -> dict[str, Any]:
    """Lê chat Evolution e atualiza funil de um único registro ``contatado``."""
    row = await repo.buscar_por_id(pool, envio_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Envio não encontrado")
    if str(row["status"]) != "contatado":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Envio não está contatado",
        )
    return (await executar_atualizar_conversas_whatsapp(pool, config, envio_id=str(envio_id))).to_dict()


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
