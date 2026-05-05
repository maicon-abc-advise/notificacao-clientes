from __future__ import annotations

import logging
import uuid

import asyncpg

from app.orquestracao.repositorios.fornecedores_repo import atualizar_contato_apos_enriquecimento
from app.orquestracao.servicos.auxiliares.porta_enriquecimento_contato import PortaEnriquecimentoContato

_log = logging.getLogger(__name__)


async def enriquecer_se_necessario(
    pool: asyncpg.Pool,
    porta: PortaEnriquecimentoContato,
    *,
    fornecedor_id: uuid.UUID,
    cnpj_basico: str,
    email_atual: str | None,
    telefone_atual: str | None,
) -> tuple[str | None, str | None]:
    """Preenche e-mail/telefone em falta via porta e persiste em `fornecedores`."""
    email = (email_atual or "").strip() or None
    telefone = (telefone_atual or "").strip() or None
    if email and telefone:
        _log.info("[orquestracao] enriquecimento: e-mail e telefone ja presentes — sem chamada a porta")
        return email, telefone

    _log.info(
        "[orquestracao] enriquecimento: chamando porta cnpj_basico=%s (faltava email=%s telefone=%s)",
        cnpj_basico,
        not email,
        not telefone,
    )
    r = await porta.enriquecer_por_cnpj_basico(cnpj_basico)
    _log.info("[orquestracao] enriquecimento: porta retornou email=%s telefone=%s", r.email, r.telefone)
    novo_email = email or (r.email.strip() if r.email else None)
    novo_tel = telefone or (r.telefone.strip() if r.telefone else None)
    if novo_email != email or novo_tel != telefone:
        await atualizar_contato_apos_enriquecimento(
            pool,
            fornecedor_id=fornecedor_id,
            email=novo_email,
            telefone=novo_tel,
        )
    return novo_email, novo_tel
