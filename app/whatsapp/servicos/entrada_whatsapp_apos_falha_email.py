"""Entrada na fila ``whatsapp_envios`` após falha de e-mail (bounce/sweep)."""

from __future__ import annotations

import logging
import uuid
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
    "whatsapp_sem_telefone",
]


async def _contar_buscas_desde(
    pool: asyncpg.Pool,
    cnpj_basico: str,
    desde,
) -> int:
    p = obter_identificadores_postgres()
    schema = p.schema
    try:
        n = await pool.fetchval(
            f"""
            SELECT COUNT(*)::int
            FROM {_q(schema)}.aparicoes
            WHERE cnpj_basico = $1 AND criado_em > $2
            """,
            cnpj_basico,
            desde,
        )
        return int(n or 0)
    except asyncpg.UndefinedTableError:
        p = obter_identificadores_postgres()
        te = p.qual("engajamento_fornecedores")
        try:
            n = await pool.fetchval(
                f"SELECT aparicoes_busca FROM {te} WHERE cnpj_basico = $1",
                cnpj_basico,
            )
            return int(n or 0)
        except asyncpg.UndefinedTableError:
            return 0


def _q(schema: str) -> str:
    if schema == "public":
        return "public"
    return f'"{schema}"'


async def _fornecedor_cadastrou(pool: asyncpg.Pool, cnpj_basico: str) -> bool:
    row = await buscar_usuario_fornecedor_por_cnpj_basico(pool, cnpj_basico)
    return row is not None


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
        n = await _contar_buscas_desde(pool, cnpj_basico, row["updated_at"])
        if n < min_buscas:
            return "whatsapp_ignorado_falha"
    return None


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
        return {"retorno": "whatsapp_sem_telefone", "origem": origem}

    tel_bruto = telefone
    if not tel_bruto:
        snap = await carregar_por_cnpj_basico(pool, cnpj)
        tel_bruto = escolher_telefone_efetivo(snap.contatos_sms, None)

    tel_bruto = (tel_bruto or "").strip()
    if not tel_bruto:
        return {"retorno": "whatsapp_sem_telefone", "origem": origem, "cnpj_basico": cnpj}

    try:
        tel = normalizar_telefone_whatsapp(tel_bruto)
    except ValueError as exc:
        _log.warning("Telefone inválido para WhatsApp cnpj=%s: %s", cnpj, exc)
        return {"retorno": "whatsapp_sem_telefone", "origem": origem, "cnpj_basico": cnpj}

    existente = await repo.buscar_por_cnpj_telefone(pool, cnpj_basico=cnpj, numero_telefone=tel)
    if existente:
        bloqueio = await _decidir_entrada_existente(pool, existente, cfg, cnpj)
        if bloqueio:
            return {
                "retorno": bloqueio,
                "origem": origem,
                "cnpj_basico": cnpj,
                "id": str(existente["id"]),
            }

    ultimo = await repo.buscar_ultimo_por_cnpj(pool, cnpj)
    if ultimo and str(ultimo["numero_telefone"]) != tel:
        bloqueio = await _decidir_entrada_existente(pool, ultimo, cfg, cnpj)
        if bloqueio in ("whatsapp_ja_na_fila", "whatsapp_ignorado_falha", "whatsapp_ignorado_cadastrado"):
            return {
                "retorno": bloqueio,
                "origem": origem,
                "cnpj_basico": cnpj,
                "id": str(ultimo["id"]),
            }

    row, inseriu = await repo.inserir_se_ausente(
        pool,
        cnpj_basico=cnpj,
        numero_telefone=tel,
        fornecedor_id=fornecedor_id,
    )
    if not inseriu or row is None:
        return {
            "retorno": "whatsapp_ja_na_fila",
            "origem": origem,
            "cnpj_basico": cnpj,
        }

    await tocar_engajamento_whatsapp(
        pool,
        fornecedor_id,
        cnpj,
        WhatsappEngajamentoEstado.WHATSAPP_PENDENTE_FILA,
        telefone=tel,
    )
    _log.info("WhatsApp inserido cnpj=%s tel=%s origem=%s id=%s", cnpj, tel, origem, row["id"])
    return {
        "retorno": "whatsapp_inserido",
        "origem": origem,
        "cnpj_basico": cnpj,
        "id": str(row["id"]),
        "numero_telefone": tel,
    }
