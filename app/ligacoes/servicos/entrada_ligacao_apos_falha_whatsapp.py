"""Enfileira ligação pendente após falha definitiva do funil WhatsApp."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Literal

import asyncpg

from app.config.postgres_identificadores import obter_identificadores_postgres
from app.ligacoes.repositorios.redis_ligacoes_pendente import RepositorioLigacoesPendenteRedis
from app.ligacoes.servicos.validacao_telefone_voz_br import telefone_para_e164
from app.orquestracao.repositorios.company_profile_repo import buscar_full_profile_por_cnpj_basico
from app.orquestracao.repositorios.fornecedores_repo import buscar_usuario_fornecedor_por_cnpj_basico
from app.reenvio.redis_app import obter_cliente_redis
from app.reenvio.servicos.engajamento_contatos import agregado_canal_bloqueado

_log = logging.getLogger(__name__)

OrigemLigacaoWhatsapp = Literal["whatsapp_sem_numero_valido", "whatsapp_etapas_esgotadas"]

RetornoEntradaLigacao = Literal[
    "ligacao_enfileirada",
    "ligacao_ja_na_fila",
    "ligacao_ignorado_cadastrado",
    "ligacao_ignorado_canal_inativo",
    "ligacao_ignorado_sem_telefone",
    "ligacao_ignorado_sem_uf",
    "ligacao_ignorado_sem_segmento",
]

_ORIGENS_VALIDAS = frozenset({"whatsapp_sem_numero_valido", "whatsapp_etapas_esgotadas"})
_repo = RepositorioLigacoesPendenteRedis()


def _resposta(
    retorno: RetornoEntradaLigacao,
    *,
    origem: str,
    cnpj_basico: str,
    id_externo: str | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "retorno": retorno,
        "origem": origem,
        "cnpj_basico": cnpj_basico,
    }
    if id_externo is not None:
        out["id_externo"] = id_externo
    return out


async def _fornecedor_cadastrou(pool: asyncpg.Pool, cnpj_basico: str) -> bool:
    try:
        await buscar_usuario_fornecedor_por_cnpj_basico(pool, cnpj_basico=cnpj_basico)
        return True
    except LookupError:
        return False


async def _engajamento_ligacao_bloqueado(pool: asyncpg.Pool, cnpj_basico: str) -> bool:
    p = obter_identificadores_postgres()
    te = p.qual("engajamento_fornecedores")
    try:
        val = await pool.fetchval(
            f"SELECT engajamento_ligacao FROM {te} WHERE cnpj_basico = $1",
            cnpj_basico,
        )
    except asyncpg.UndefinedColumnError:
        return False
    return agregado_canal_bloqueado(str(val or ""))


async def _pendente_ligacao_para_cnpj(cnpj_basico: str) -> bool:
    redis = await obter_cliente_redis()
    itens = await _repo.listar_pendentes(redis, limite=500)
    return any(str(item.get("cnpj_basico") or "").strip() == cnpj_basico for item in itens)


async def _resolver_segmento(pool: asyncpg.Pool, cnpj_basico: str) -> str | None:
    profile, _uf = await buscar_full_profile_por_cnpj_basico(pool, cnpj_basico=cnpj_basico)
    if profile:
        for chave in ("industria", "segmento", "v_produto", "v_servico"):
            val = profile.get(chave)
            if val and str(val).strip():
                return str(val).strip()
    return None


async def _resolver_uf(pool: asyncpg.Pool, cnpj_basico: str) -> str | None:
    profile, uf_col = await buscar_full_profile_por_cnpj_basico(pool, cnpj_basico=cnpj_basico)
    uf = (uf_col or "").strip().upper()
    if len(uf) == 2:
        return uf
    if profile:
        for chave in ("uf", "estado", "uf_buscada"):
            raw = profile.get(chave)
            if raw:
                cand = str(raw).strip().upper()[:2]
                if len(cand) == 2:
                    return cand
    return None


async def _resolver_nome_empresa(pool: asyncpg.Pool, cnpj_basico: str) -> str | None:
    p = obter_identificadores_postgres()
    te = p.qual("engajamento_fornecedores")
    nome = await pool.fetchval(
        f"SELECT NULLIF(btrim(nome_fantasia), '') FROM {te} WHERE cnpj_basico = $1",
        cnpj_basico,
    )
    if nome and str(nome).strip():
        return str(nome).strip()
    profile, _ = await buscar_full_profile_por_cnpj_basico(pool, cnpj_basico=cnpj_basico)
    if profile:
        for chave in ("nome_fantasia", "nome", "razao_social"):
            val = profile.get(chave)
            if val and str(val).strip():
                return str(val).strip()
    return None


async def _resolver_quantidade_buscas(pool: asyncpg.Pool, cnpj_basico: str) -> int:
    p = obter_identificadores_postgres()
    te = p.qual("engajamento_fornecedores")
    n = await pool.fetchval(
        f"SELECT aparicoes_busca FROM {te} WHERE cnpj_basico = $1",
        cnpj_basico,
    )
    return max(int(n or 0), 0)


async def entrada_ligacao_apos_falha_whatsapp(
    pool: asyncpg.Pool,
    *,
    cnpj_basico: str,
    telefone: str,
    origem: OrigemLigacaoWhatsapp,
    fornecedor_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Coloca ligação na fila Redis após falha definitiva do WhatsApp."""
    cnpj = (cnpj_basico or "").strip()
    if not cnpj:
        return _resposta("ligacao_ignorado_sem_telefone", origem=origem, cnpj_basico="")

    if origem not in _ORIGENS_VALIDAS:
        raise ValueError(f"origem inválida para ligação pós-WhatsApp: {origem!r}")

    if await _fornecedor_cadastrou(pool, cnpj):
        return _resposta("ligacao_ignorado_cadastrado", origem=origem, cnpj_basico=cnpj)

    if await _engajamento_ligacao_bloqueado(pool, cnpj):
        return _resposta("ligacao_ignorado_canal_inativo", origem=origem, cnpj_basico=cnpj)

    if await _pendente_ligacao_para_cnpj(cnpj):
        return _resposta("ligacao_ja_na_fila", origem=origem, cnpj_basico=cnpj)

    tel_e164 = telefone_para_e164(telefone)
    if not tel_e164:
        return _resposta("ligacao_ignorado_sem_telefone", origem=origem, cnpj_basico=cnpj)

    uf = await _resolver_uf(pool, cnpj)
    if not uf or len(uf) != 2:
        return _resposta("ligacao_ignorado_sem_uf", origem=origem, cnpj_basico=cnpj)

    segmento = await _resolver_segmento(pool, cnpj)
    if not segmento:
        return _resposta("ligacao_ignorado_sem_segmento", origem=origem, cnpj_basico=cnpj)

    qtd = await _resolver_quantidade_buscas(pool, cnpj)
    nome = await _resolver_nome_empresa(pool, cnpj)

    id_externo = str(uuid.uuid4())
    redis = await obter_cliente_redis()
    ok = await _repo.criar(
        redis,
        id_externo=id_externo,
        telefone=tel_e164,
        cnpj_basico=cnpj,
        quantidade_buscas=qtd,
        uf_buscada=uf,
        segmento_buscado=segmento,
        origem=origem,
        nome_empresa=nome,
        fornecedor_id=str(fornecedor_id) if fornecedor_id else None,
    )
    if not ok:
        return _resposta("ligacao_ja_na_fila", origem=origem, cnpj_basico=cnpj)

    _log.info(
        "Ligação enfileirada após falha WhatsApp cnpj=%s origem=%s id_externo=%s",
        cnpj,
        origem,
        id_externo,
    )
    return _resposta("ligacao_enfileirada", origem=origem, cnpj_basico=cnpj, id_externo=id_externo)


async def convidar_ligacao_apos_falha_whatsapp(
    pool: asyncpg.Pool,
    row: asyncpg.Record | dict[str, Any],
    *,
    origem: OrigemLigacaoWhatsapp,
) -> dict[str, Any]:
    """Atalho a partir de uma linha ``whatsapp_envios``."""
    cnpj = str(row.get("cnpj_basico") or row.get("cnpj_empresa") or "").strip()
    telefone = str(row.get("numero_telefone") or "").strip()
    fid = row.get("fornecedor_id")
    fornecedor_id = fid if isinstance(fid, uuid.UUID) else None
    if fornecedor_id is None and fid:
        try:
            fornecedor_id = uuid.UUID(str(fid))
        except ValueError:
            fornecedor_id = None
    return await entrada_ligacao_apos_falha_whatsapp(
        pool,
        cnpj_basico=cnpj,
        telefone=telefone,
        origem=origem,
        fornecedor_id=fornecedor_id,
    )
