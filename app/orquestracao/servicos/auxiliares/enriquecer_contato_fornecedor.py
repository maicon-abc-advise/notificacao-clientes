from __future__ import annotations

import logging

from app.orquestracao.servicos.auxiliares.porta_enriquecimento_contato import (
    PortaEnriquecimentoContato,
    ResultadoEnriquecimentoContato,
)
from app.reenvio.servicos.engajamento_contatos import normalizar_email
from app.reenvio.servicos.validacao_telefone_sms_br import normalizar_telefone_movel_br_para_sms

_log = logging.getLogger(__name__)


def _tupla_um_email(email_atual: str | None) -> tuple[str, ...]:
    n = normalizar_email(email_atual)
    return (n,) if n else ()


def _tupla_um_telefone(telefone_atual: str | None) -> tuple[str, ...]:
    n = normalizar_telefone_movel_br_para_sms(telefone_atual)
    return (n,) if n else ()


def _merge_email_lists(primary_parts: tuple[str, ...], from_porta: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for e in list(primary_parts) + list(from_porta):
        n = normalizar_email(e) if e else ""
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return tuple(out)


def _merge_tel_lists(primary_parts: tuple[str, ...], from_porta: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for e in list(primary_parts) + list(from_porta):
        canon = normalizar_telefone_movel_br_para_sms(e)
        if canon and canon not in seen:
            seen.add(canon)
            out.append(canon)
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
        emails_payload=_tupla_um_email(email_atual),
        telefones_payload=_tupla_um_telefone(telefone_atual),
    )
    return r.email, r.telefone


async def enriquecer_retorno_completo(
    porta: PortaEnriquecimentoContato,
    *,
    cnpj_basico: str,
    emails_payload: tuple[str, ...],
    telefones_payload: tuple[str, ...],
) -> ResultadoEnriquecimentoContato:
    """Igual ao fluxo de enriquecimento, mas devolve também listas para ``engajamento_fornecedores``."""
    tem_email = bool(emails_payload)
    tem_tel = bool(telefones_payload)
    if tem_email and tem_tel:
        _log.info("[orquestracao] enriquecimento: e-mail e telefone ja presentes — sem chamada a porta")
        emails_m = _merge_email_lists(emails_payload, ())
        tels_m = _merge_tel_lists(telefones_payload, ())
        return ResultadoEnriquecimentoContato(
            email=emails_m[0] if emails_m else None,
            telefone=tels_m[0] if tels_m else None,
            emails=emails_m,
            telefones=tels_m,
        )

    _log.info(
        "[orquestracao] enriquecimento: chamando porta cnpj_basico=%s (faltava email=%s telefone=%s)",
        cnpj_basico,
        not tem_email,
        not tem_tel,
    )
    r = await porta.enriquecer_por_cnpj_basico(cnpj_basico)
    emails_m = _merge_email_lists(emails_payload, r.emails)
    tels_m = _merge_tel_lists(telefones_payload, r.telefones)
    pe = emails_m[0] if emails_m else None
    pt = tels_m[0] if tels_m else None
    _log.info("[orquestracao] enriquecimento: resultado email=%s telefone=%s listas=%s/%s", pe, pt, len(emails_m), len(tels_m))
    return ResultadoEnriquecimentoContato(email=pe, telefone=pt, emails=emails_m, telefones=tels_m)
