"""Entrada na fila ``whatsapp_envios`` após falha de e-mail (bounce/sweep)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Literal

import asyncpg

from app.config.config import Configuracao
from app.config.postgres_identificadores import obter_identificadores_postgres
from app.orquestracao.repositorios.engajamento_consulta_repo import carregar_por_cnpj_basico
from app.orquestracao.repositorios.fornecedores_repo import buscar_usuario_fornecedor_por_cnpj_basico
from app.reenvio.servicos.engajamento_contatos import escolher_telefone_efetivo
from app.whatsapp.repositorios import postgres_whatsapp_envios as repo
from app.whatsapp.servicos.telefone_whatsapp import normalizar_telefone_whatsapp
from app.whatsapp.servicos.tocar_engajamento_whatsapp import tocar_engajamento_whatsapp, WhatsappEngajamentoEstado

_log = logging.getLogger(__name__)

RetornoEntrada = Literal[
    "whatsapp_inserido",
    "whatsapp_ja_na_fila",
    "whatsapp_ignorado_falha",
    "whatsapp_ignorado_cadastrado",
    "whatsapp_ignorado_poucas_buscas",
    "whatsapp_sem_telefone",
]

_ORIGEM_ISENTA_APARICOES = frozenset({"proximo_telefone_invalido", "dashboard_manual"})


def _q(schema: str) -> str:
    if schema == "public":
        return "public"
    return f'"{schema}"'


async def _contar_aparicoes(
    pool: asyncpg.Pool,
    cnpj_basico: str,
    *,
    desde: datetime | None = None,
) -> int:
    """Conta linhas em ``aparicoes`` para o CNPJ (total ou desde um instante)."""
    p = obter_identificadores_postgres()
    schema = p.schema
    if desde is None:
        sql = f"""
            SELECT COUNT(*)::int
            FROM {_q(schema)}.aparicoes
            WHERE cnpj_basico = $1
        """
        params: list[object] = [cnpj_basico]
    else:
        sql = f"""
            SELECT COUNT(*)::int
            FROM {_q(schema)}.aparicoes
            WHERE cnpj_basico = $1 AND created_at > $2
        """
        params = [cnpj_basico, desde]
    try:
        n = await pool.fetchval(sql, *params)
        return int(n or 0)
    except asyncpg.UndefinedTableError:
        _log.warning("Tabela aparicoes indisponível para cnpj_basico=%s", cnpj_basico)
        return 0


async def _fornecedor_cadastrou(pool: asyncpg.Pool, cnpj_basico: str) -> bool:
    try:
        await buscar_usuario_fornecedor_por_cnpj_basico(pool, cnpj_basico=cnpj_basico)
        return True
    except LookupError:
        return False


def _resposta_entrada(
    retorno: RetornoEntrada,
    *,
    origem: str,
    cnpj_basico: str,
    id_registro: str | None = None,
    aparicoes: int | None = None,
    minimo: int | None = None,
) -> dict:
    out: dict = {
        "retorno": retorno,
        "origem": origem,
        "cnpj_basico": cnpj_basico,
    }
    if id_registro is not None:
        out["id"] = id_registro
    if aparicoes is not None:
        out["aparicoes"] = aparicoes
    if minimo is not None:
        out["minimo"] = minimo
    return out


async def _decidir_entrada_existente(
    pool: asyncpg.Pool,
    row: asyncpg.Record,
    cfg: Configuracao,
    cnpj_basico: str,
) -> RetornoEntrada | None:
    status = str(row["status"])
    if status in ("pendente", "contatado"):
        return "whatsapp_ja_na_fila"
    if status == "concluido_sucesso":
        if await _fornecedor_cadastrou(pool, cnpj_basico):
            return "whatsapp_ignorado_cadastrado"
        return "whatsapp_ignorado_cadastrado"
    if status == "concluido_falha":
        min_buscas = cfg.routine_min_buscas
        n = await _contar_aparicoes(pool, cnpj_basico, desde=row["updated_at"])
        if n < min_buscas:
            return "whatsapp_ignorado_falha"
    return None


async def _bloquear_poucas_aparicoes_primeira_entrada(
    pool: asyncpg.Pool,
    cfg: Configuracao,
    *,
    cnpj_basico: str,
    origem: str,
    ultimo: asyncpg.Record | None,
) -> dict | None:
    """Exige ``routine_min_buscas`` em ``aparicoes`` na primeira entrada do CNPJ na fila."""
    if origem in _ORIGEM_ISENTA_APARICOES:
        return None
    if ultimo is not None:
        return None
    min_buscas = cfg.routine_min_buscas_primeira_entrada
    n = await _contar_aparicoes(pool, cnpj_basico)
    if n >= min_buscas:
        return None
    _log.info(
        "WhatsApp ignorado (poucas aparições) cnpj=%s aparicoes=%s minimo=%s origem=%s",
        cnpj_basico,
        n,
        min_buscas,
        origem,
    )
    return _resposta_entrada(
        "whatsapp_ignorado_poucas_buscas",
        origem=origem,
        cnpj_basico=cnpj_basico,
        aparicoes=n,
        minimo=min_buscas,
    )


async def entrada_whatsapp_apos_falha_email(
    pool: asyncpg.Pool,
    cfg: Configuracao,
    *,
    cnpj_basico: str,
    fornecedor_id: uuid.UUID | None,
    origem: str,
    telefone: str | None = None,
) -> dict:
    """
    Centraliza dedup e INSERT em ``whatsapp_envios``.
    Se ``telefone`` omitido, usa ``escolher_telefone_efetivo`` do engajamento.
    """
    cnpj = (cnpj_basico or "").strip()
    if not cnpj:
        return _resposta_entrada("whatsapp_sem_telefone", origem=origem, cnpj_basico="")

    tel_bruto = telefone
    if not tel_bruto:
        snap = await carregar_por_cnpj_basico(pool, cnpj)
        tel_bruto = escolher_telefone_efetivo(snap.contatos_sms, None)

    tel_bruto = (tel_bruto or "").strip()
    if not tel_bruto:
        return _resposta_entrada("whatsapp_sem_telefone", origem=origem, cnpj_basico=cnpj)

    try:
        tel = normalizar_telefone_whatsapp(tel_bruto)
    except ValueError as exc:
        _log.warning("Telefone inválido para WhatsApp cnpj=%s: %s", cnpj, exc)
        return _resposta_entrada("whatsapp_sem_telefone", origem=origem, cnpj_basico=cnpj)

    existente = await repo.buscar_por_cnpj_telefone(pool, cnpj_basico=cnpj, numero_telefone=tel)
    if existente:
        bloqueio = await _decidir_entrada_existente(pool, existente, cfg, cnpj)
        if bloqueio:
            return _resposta_entrada(
                bloqueio,
                origem=origem,
                cnpj_basico=cnpj,
                id_registro=str(existente["id"]),
            )

    ultimo = await repo.buscar_ultimo_por_cnpj(pool, cnpj)
    if ultimo and str(ultimo["numero_telefone"]) != tel:
        bloqueio = await _decidir_entrada_existente(pool, ultimo, cfg, cnpj)
        if bloqueio in ("whatsapp_ja_na_fila", "whatsapp_ignorado_falha", "whatsapp_ignorado_cadastrado"):
            return _resposta_entrada(
                bloqueio,
                origem=origem,
                cnpj_basico=cnpj,
                id_registro=str(ultimo["id"]),
            )

    bloqueio_aparicoes = await _bloquear_poucas_aparicoes_primeira_entrada(
        pool,
        cfg,
        cnpj_basico=cnpj,
        origem=origem,
        ultimo=ultimo,
    )
    if bloqueio_aparicoes is not None:
        return bloqueio_aparicoes

    row, inseriu = await repo.inserir_se_ausente(
        pool,
        cnpj_basico=cnpj,
        numero_telefone=tel,
        fornecedor_id=fornecedor_id,
    )
    if not inseriu or row is None:
        return _resposta_entrada(
            "whatsapp_ja_na_fila",
            origem=origem,
            cnpj_basico=cnpj,
        )

    await tocar_engajamento_whatsapp(
        pool,
        fornecedor_id,
        cnpj,
        WhatsappEngajamentoEstado.WHATSAPP_PENDENTE_FILA,
        telefone=tel,
    )
    _log.info("WhatsApp inserido cnpj=%s tel=%s origem=%s id=%s", cnpj, tel, origem, row["id"])
    out = _resposta_entrada(
        "whatsapp_inserido",
        origem=origem,
        cnpj_basico=cnpj,
        id_registro=str(row["id"]),
    )
    out["numero_telefone"] = tel
    return out
