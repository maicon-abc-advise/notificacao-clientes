"""Criação de ligação pendente e disparo manual via dashboard."""

from __future__ import annotations

import re
import uuid
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import HTTPException
from redis.asyncio import Redis

from app.config.config import obter_configuracao
from app.dashboard.servicos.exibicao import enriquecer_redis_ligacao_pendente
from app.ligacoes.repositorios.redis_ligacoes_pendente import RepositorioLigacoesPendenteRedis
from app.ligacoes.api.externo.vapi.adaptador_envio import ErroEnvioVapi
from app.ligacoes.servicos.executar_dispatch_call import (
    executar_dispatch_call,
    fornecedor_id_de_hash,
    pedido_de_hash_redis,
)
from app.ligacoes.servicos.validacao_telefone_voz_br import telefone_para_e164
from app.reenvio.servicos.n8n_claims import claim_n8n_ativo, liberar_claim_item_n8n

_ORIGEM_DASHBOARD = "dashboard-manual"
_CNPJ_RE = re.compile(r"^\d{8}$")
_repo = RepositorioLigacoesPendenteRedis()


def _normalizar_cnpj_basico(cnpj: str) -> str:
    dig = re.sub(r"\D", "", (cnpj or "").strip())
    if not _CNPJ_RE.match(dig):
        raise HTTPException(status_code=400, detail="cnpj_basico deve ter 8 dígitos")
    return dig


async def criar_ligacao_pendente_dashboard(
    redis: Redis,
    *,
    telefone: str,
    cnpj_basico: str,
    quantidade_buscas: int,
    uf_buscada: str,
    segmento_buscado: str,
    nome_empresa: str | None = None,
    fornecedor_id: UUID | None = None,
) -> dict[str, Any]:
    tel = telefone_para_e164(telefone)
    if not tel:
        raise HTTPException(status_code=400, detail="telefone inválido para ligação de voz")
    cnpj_b = _normalizar_cnpj_basico(cnpj_basico)
    uf = (uf_buscada or "").strip().upper()
    if len(uf) != 2:
        raise HTTPException(status_code=400, detail="uf_buscada deve ter 2 letras")
    segmento = (segmento_buscado or "").strip()
    if not segmento:
        raise HTTPException(status_code=400, detail="segmento_buscado obrigatório")

    id_externo = str(uuid.uuid4())
    ok = await _repo.criar(
        redis,
        id_externo=id_externo,
        telefone=tel,
        cnpj_basico=cnpj_b,
        quantidade_buscas=quantidade_buscas,
        uf_buscada=uf,
        segmento_buscado=segmento,
        origem=_ORIGEM_DASHBOARD,
        nome_empresa=(nome_empresa or "").strip() or None,
        fornecedor_id=str(fornecedor_id) if fornecedor_id else None,
    )
    if not ok:
        raise HTTPException(status_code=409, detail="id_externo já existe na fila")

    return await _carregar_linha_pendente(redis, id_externo=id_externo)


async def _carregar_linha_pendente(redis: Redis, *, id_externo: str) -> dict[str, Any]:
    itens = await _repo.listar_pendentes(redis, limite=500)
    item = next((i for i in itens if i.get("id_externo") == id_externo), None)
    if not item:
        raw = await _repo.obter_hash(redis, id_externo)
        if not raw:
            raise HTTPException(status_code=404, detail="pendente não encontrado")
        qtd_raw = raw.get("quantidade_buscas") or "0"
        try:
            qtd = int(qtd_raw)
        except ValueError:
            qtd = 0
        item = {
            "id_externo": raw.get("id_externo") or id_externo,
            "telefone": raw.get("telefone", ""),
            "cnpj_basico": raw.get("cnpj_basico") or None,
            "quantidade_buscas": qtd,
            "uf_buscada": raw.get("uf_buscada") or None,
            "segmento_buscado": raw.get("segmento_buscado") or None,
            "nome_empresa": raw.get("nome_empresa") or None,
            "fornecedor_id": raw.get("fornecedor_id") or None,
            "origem": raw.get("origem", ""),
            "criado_em": raw.get("criado_em"),
        }
    item["claim_n8n_ativo"] = await claim_n8n_ativo(redis, canal="ligacao", id_externo=id_externo)
    return enriquecer_redis_ligacao_pendente(item)


async def disparar_ligacao_pendente_dashboard(
    pool: asyncpg.Pool,
    redis: Redis,
    *,
    id_externo: str,
) -> dict[str, Any]:
    ext = (id_externo or "").strip()
    if not ext:
        raise HTTPException(status_code=400, detail="id_externo obrigatório")

    if await claim_n8n_ativo(redis, canal="ligacao", id_externo=ext):
        raise HTTPException(
            status_code=409,
            detail="item reservado pelo n8n (claim ativo); tente novamente em alguns minutos",
        )

    raw = await _repo.obter_hash(redis, ext)
    if not raw:
        raise HTTPException(status_code=404, detail="pendente não encontrado")

    config = obter_configuracao()
    pedido = pedido_de_hash_redis(raw, ext)
    fid = fornecedor_id_de_hash(raw)

    try:
        resultado = await executar_dispatch_call(pool, pedido, config=config, fornecedor_id=fid)
        await _repo.remover(redis, ext)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ErroEnvioVapi as e:
        raise HTTPException(status_code=502, detail=str(e)[:2000]) from e
    finally:
        await liberar_claim_item_n8n(redis, canal="ligacao", id_externo=ext)

    return resultado
