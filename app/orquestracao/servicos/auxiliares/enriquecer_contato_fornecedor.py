from __future__ import annotations

import logging

from app.orquestracao.servicos.auxiliares.porta_enriquecimento_contato import (
    PortaEnriquecimentoContato,
    ResultadoEnriquecimentoContato,
)
from app.reenvio.servicos.engajamento_contatos import normalizar_email, normalizar_telefone

_log = logging.getLogger(__name__)


def _merge_email_lists(primary: str | None, from_porta: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for e in ([primary] if primary else []) + list(from_porta):
        n = normalizar_email(e) if e else ""
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return tuple(out)


def _merge_tel_lists(primary: str | None, from_porta: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for e in ([primary] if primary else []) + list(from_porta):
        n = normalizar_telefone(e) if e else ""
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return tuple(out)


async def enriquecer_se_necessario(
    porta: PortaEnriquecimentoContato,
    *,
    cnpj_basico: str,
    email_atual: str | None,
    telefone_atual: str | None,
) -> tuple[str | None, str | None]:
    """Preenche e-mail/telefone em falta via porta (sem persistir no usuário)."""
    r = await enriquecer_retorno_completo(
        porta,
        cnpj_basico=cnpj_basico,
        email_atual=email_atual,
        telefone_atual=telefone_atual,
    )
    return r.email, r.telefone


async def enriquecer_retorno_completo(
    porta: PortaEnriquecimentoContato,
    *,
    cnpj_basico: str,
    email_atual: str | None,
    telefone_atual: str | None,
) -> ResultadoEnriquecimentoContato:
    """Igual ao fluxo de enriquecimento, mas devolve também listas para ``engajamento_fornecedores``."""
    email = (email_atual or "").strip() or None
    telefone = (telefone_atual or "").strip() or None
    if email and telefone:
        _log.info("[orquestracao] enriquecimento: e-mail e telefone ja presentes — sem chamada a porta")
        emails_m = _merge_email_lists(email, ())
        tels_m = _merge_tel_lists(telefone, ())
        return ResultadoEnriquecimentoContato(
            email=emails_m[0] if emails_m else None,
            telefone=tels_m[0] if tels_m else None,
            emails=emails_m,
            telefones=tels_m,
        )

    _log.info(
        "[orquestracao] enriquecimento: chamando porta cnpj_basico=%s (faltava email=%s telefone=%s)",
        cnpj_basico,
        not email,
        not telefone,
    )
    r = await porta.enriquecer_por_cnpj_basico(cnpj_basico)
    emails_m = _merge_email_lists(email, r.emails)
    tels_m = _merge_tel_lists(telefone, r.telefones)
    pe = emails_m[0] if emails_m else None
    pt = tels_m[0] if tels_m else None
    _log.info("[orquestracao] enriquecimento: resultado email=%s telefone=%s listas=%s/%s", pe, pt, len(emails_m), len(tels_m))
    return ResultadoEnriquecimentoContato(email=pe, telefone=pt, emails=emails_m, telefones=tels_m)
