"""Marca compradores elegíveis como convertidos se acessaram a plataforma (n_acessos > 1)."""

from __future__ import annotations

import logging

import asyncpg

from app.config.postgres_identificadores import obter_identificadores_postgres
from app.orquestracao.api.dto.sincronizar_conversoes_compradores_dto import (
    RespostaSincronizarConversoesCompradores,
)
from app.orquestracao.repositorios import engajamento_compradores_repo

_log = logging.getLogger(__name__)


async def executar_sincronizar_conversoes_compradores(
    pool: asyncpg.Pool,
) -> RespostaSincronizarConversoesCompradores:
    p = obter_identificadores_postgres()
    tc = p.qual("engajamento_compradores")
    tu = p.qual("usuario_comprador")

    avaliados = int(
        await pool.fetchval(
            f"""
            SELECT COUNT(*)::bigint
            FROM {tc}
            WHERE primeira_consulta_sem_cadastro = true
              AND converteu = false
            """
        )
        or 0
    )

    rows = await pool.fetch(
        f"""
        SELECT DISTINCT ec.telefone
        FROM {tc} ec
        INNER JOIN {tu} uc
          ON regexp_replace(COALESCE(uc.telefone, ''), '\\D', '', 'g')
           = regexp_replace(ec.telefone, '\\D', '', 'g')
        WHERE ec.primeira_consulta_sem_cadastro = true
          AND ec.converteu = false
          AND COALESCE(uc.n_acessos, 0) > 1
        """
    )

    convertidos = 0
    for row in rows:
        tel = (row["telefone"] or "").strip()
        if not tel:
            continue
        if await engajamento_compradores_repo.marcar_convertido_por_telefone(pool, telefone=tel):
            convertidos += 1

    _log.info(
        "Sync conversões compradores (n_acessos>1): avaliados=%s convertidos=%s",
        avaliados,
        convertidos,
    )
    return RespostaSincronizarConversoesCompradores(
        avaliados=avaliados,
        convertidos=convertidos,
    )
