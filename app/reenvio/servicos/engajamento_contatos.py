"""Listas JSON de contatos em ``engajamento_fornecedores`` e rollup para estados agregados."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from app.reenvio.servicos.engajamento_estado import (
    EngajamentoCanalAgregado,
    EngajamentoEmailEstado,
    EngajamentoSmsEstado,
)


def agregado_canal_bloqueado(valor_agregado: str | None) -> bool:
    """True se o agregado do canal está INATIVO (não usar o canal)."""
    return (valor_agregado or "").strip().lower() == EngajamentoCanalAgregado.INATIVO.value

_EMAIL_BLOQUEIA_ENVIO = frozenset(
    {
        EngajamentoEmailEstado.EMAIL_BOUNCE_HARD_SEM_SMS.value,
        EngajamentoEmailEstado.EMAIL_BOUNCE_HARD_SMS_FILA.value,
        EngajamentoEmailEstado.EMAIL_NAO_EXISTE.value,
        EngajamentoEmailEstado.EMAIL_FALHA_RECUPERAVEL_MAILBOX_FULL.value,
        EngajamentoEmailEstado.EMAIL_FALHA_RECUPERAVEL_TEMPORARY.value,
        EngajamentoEmailEstado.EMAIL_FALHA_RECUPERAVEL_UNKNOWN.value,
        EngajamentoEmailEstado.EMAIL_ENVIADO_API.value,
        EngajamentoEmailEstado.EMAIL_WEBHOOK_SENT.value,
        EngajamentoEmailEstado.EMAIL_SWEEP_PROXIMO_EMAIL.value,
        EngajamentoEmailEstado.EMAIL_SWEEP_LEMBRETE_SMS.value,
    }
)

_SMS_BLOQUEIA_ENVIO = frozenset(
    {
        EngajamentoSmsEstado.SMS_FALHA_NUMERO.value,
        EngajamentoSmsEstado.SMS_FALHA_LIMITE.value,
        EngajamentoSmsEstado.SMS_NAO_EXISTE.value,
        EngajamentoSmsEstado.SMS_NUMERO_INVALIDO.value,
        EngajamentoSmsEstado.SMS_ENVIADO_API.value,
        EngajamentoSmsEstado.SMS_WEBHOOK_SENT.value,
        EngajamentoSmsEstado.SMS_REPROCESSAR_FILA.value,
    }
)

_EMAIL_GOOD_AGG = frozenset(
    {
        EngajamentoEmailEstado.ATIVO.value,
        EngajamentoEmailEstado.EMAIL_ENTREGUE_CAIXA.value,
        EngajamentoEmailEstado.EMAIL_LIDO.value,
        EngajamentoEmailEstado.EMAIL_LINK_CLICADO.value,
    }
)

_EMAIL_PENDING_AGG = frozenset(
    {
        EngajamentoEmailEstado.EMAIL_ENVIADO_API.value,
        EngajamentoEmailEstado.EMAIL_WEBHOOK_SENT.value,
        EngajamentoEmailEstado.EMAIL_SWEEP_PROXIMO_EMAIL.value,
        EngajamentoEmailEstado.EMAIL_FALHA_RECUPERAVEL_MAILBOX_FULL.value,
        EngajamentoEmailEstado.EMAIL_FALHA_RECUPERAVEL_TEMPORARY.value,
        EngajamentoEmailEstado.EMAIL_FALHA_RECUPERAVEL_UNKNOWN.value,
    }
)

_EMAIL_TERMINAL_INATIVO = frozenset(
    {
        EngajamentoEmailEstado.EMAIL_BOUNCE_HARD_SEM_SMS.value,
        EngajamentoEmailEstado.EMAIL_BOUNCE_HARD_SMS_FILA.value,
        EngajamentoEmailEstado.EMAIL_NAO_EXISTE.value,
        EngajamentoEmailEstado.EMAIL_SWEEP_LEMBRETE_SMS.value,
    }
)

_SMS_GOOD_AGG = frozenset(
    {
        EngajamentoSmsEstado.ATIVO.value,
        EngajamentoSmsEstado.SMS_ENTREGUE.value,
        EngajamentoSmsEstado.SMS_LINK_CLICADO.value,
    }
)

_SMS_PENDING_AGG = frozenset(
    {
        EngajamentoSmsEstado.SMS_ENVIADO_API.value,
        EngajamentoSmsEstado.SMS_WEBHOOK_SENT.value,
        EngajamentoSmsEstado.SMS_REPROCESSAR_FILA.value,
    }
)

_SMS_TERMINAL_INATIVO = frozenset(
    {
        EngajamentoSmsEstado.SMS_FALHA_NUMERO.value,
        EngajamentoSmsEstado.SMS_FALHA_LIMITE.value,
        EngajamentoSmsEstado.SMS_NAO_EXISTE.value,
        EngajamentoSmsEstado.SMS_NUMERO_INVALIDO.value,
    }
)


def agora_iso() -> str:
    return datetime.now(UTC).isoformat()


def normalizar_email(endereco: str | None) -> str:
    return (endereco or "").strip().lower()


def normalizar_telefone(endereco: str | None) -> str:
    """Apenas dígitos (ex.: (55) 35... → 5535...)."""
    raw = (endereco or "").strip()
    if not raw:
        return ""
    return re.sub(r"\D", "", raw)


def parse_contatos_json(val: Any) -> list[dict[str, Any]]:
    if val is None:
        return []
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return []
        try:
            val = json.loads(s)
        except json.JSONDecodeError:
            return []
    if isinstance(val, dict):
        val = [val]
    if not isinstance(val, list):
        return []
    out: list[dict[str, Any]] = []
    for x in val:
        if isinstance(x, dict) and x.get("endereco"):
            out.append(dict(x))
    return out


def fundir_lista_contatos_email(
    existentes: list[dict[str, Any]],
    novos: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Preserva estados já gravados; acrescenta só endereços novos (payload / company_profile)."""
    by_k: dict[str, dict[str, Any]] = {}
    for c in existentes:
        k = normalizar_email(str(c.get("endereco") or ""))
        if k:
            by_k[k] = dict(c)
    for c in novos:
        k = normalizar_email(str(c.get("endereco") or ""))
        if not k:
            continue
        if k not in by_k:
            by_k[k] = dict(c)
    return list(by_k.values())


def fundir_lista_contatos_sms(
    existentes: list[dict[str, Any]],
    novos: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_k: dict[str, dict[str, Any]] = {}
    for c in existentes:
        k = normalizar_telefone(str(c.get("endereco") or ""))
        if k:
            by_k[k] = dict(c)
    for c in novos:
        k = normalizar_telefone(str(c.get("endereco") or ""))
        if not k:
            continue
        if k not in by_k:
            by_k[k] = dict(c)
    return list(by_k.values())


def contatos_incluem_email(contatos: list[dict[str, Any]], endereco: str | None) -> bool:
    n = normalizar_email(endereco)
    if not n:
        return False
    return any(normalizar_email(str(c.get("endereco") or "")) == n for c in contatos)


def contatos_incluem_telefone(contatos: list[dict[str, Any]], endereco: str | None) -> bool:
    t = normalizar_telefone(endereco)
    if not t:
        return False
    return any(normalizar_telefone(str(c.get("endereco") or "")) == t for c in contatos)


def merge_contato(
    lista: list[dict[str, Any]],
    endereco_norm: str,
    estado: str,
    *,
    now_iso: str,
    permitir_novo: bool = True,
) -> bool:
    n = normalizar_email(endereco_norm)
    for c in lista:
        if normalizar_email(str(c.get("endereco") or "")) == n:
            c["endereco"] = n
            c["estado"] = estado
            c["ultima_atualizacao_em"] = now_iso
            return True
    if not permitir_novo:
        return False
    lista.append({"endereco": n, "estado": estado, "ultima_atualizacao_em": now_iso})
    return True


def merge_contato_sms(
    lista: list[dict[str, Any]],
    endereco_norm: str,
    estado: str,
    *,
    now_iso: str,
    permitir_novo: bool = True,
) -> bool:
    t_norm = normalizar_telefone(endereco_norm)
    for c in lista:
        if normalizar_telefone(str(c.get("endereco") or "")) == t_norm:
            c["endereco"] = t_norm
            c["estado"] = estado
            c["ultima_atualizacao_em"] = now_iso
            return True
    if not permitir_novo:
        return False
    lista.append({"endereco": t_norm, "estado": estado, "ultima_atualizacao_em": now_iso})
    return True


def estado_granular_email(contatos: list[dict[str, Any]], endereco: str | None) -> str:
    if not endereco:
        return EngajamentoEmailEstado.ATIVO.value
    n = normalizar_email(endereco)
    for c in contatos:
        if normalizar_email(str(c.get("endereco") or "")) == n:
            return str(c.get("estado") or EngajamentoEmailEstado.ATIVO.value)
    return EngajamentoEmailEstado.ATIVO.value


def estado_granular_sms(contatos: list[dict[str, Any]], endereco: str | None) -> str:
    if not endereco:
        return EngajamentoSmsEstado.ATIVO.value
    n = normalizar_telefone(endereco)
    for c in contatos:
        if normalizar_telefone(str(c.get("endereco") or "")) == n:
            return str(c.get("estado") or EngajamentoSmsEstado.ATIVO.value)
    return EngajamentoSmsEstado.ATIVO.value


def email_granular_bloqueia_notificacao(estado: str) -> bool:
    return estado in _EMAIL_BLOQUEIA_ENVIO


def sms_granular_bloqueia_notificacao(estado: str) -> bool:
    return estado in _SMS_BLOQUEIA_ENVIO


def algum_email_ainda_tentavel(contatos: list[dict[str, Any]]) -> bool:
    for c in contatos:
        st = str(c.get("estado") or "")
        if st not in _EMAIL_TERMINAL_INATIVO:
            return True
    return False


def algum_sms_ainda_tentavel(contatos: list[dict[str, Any]]) -> bool:
    for c in contatos:
        st = str(c.get("estado") or "")
        if st not in _SMS_TERMINAL_INATIVO:
            return True
    return False


def algum_email_disponivel_para_envio(contatos: list[dict[str, Any]]) -> bool:
    """True se ainda existe e-mail utilizável para novo envio neste canal."""
    for c in contatos:
        st = str(c.get("estado") or "")
        if not email_granular_bloqueia_notificacao(st):
            return True
    return False


def algum_sms_disponivel_para_envio(contatos: list[dict[str, Any]]) -> bool:
    """True se ainda existe telefone utilizável para novo envio neste canal."""
    for c in contatos:
        st = str(c.get("estado") or "")
        if not sms_granular_bloqueia_notificacao(st):
            return True
    return False


def rollup_engajamento_email(
    contatos: list[dict[str, Any]],
    ultimo_envio_endereco: str | None,
) -> EngajamentoCanalAgregado:
    if not contatos:
        return EngajamentoCanalAgregado.INATIVO
    if not algum_email_ainda_tentavel(contatos):
        return EngajamentoCanalAgregado.INATIVO
    ultimo = (ultimo_envio_endereco or "").strip()
    if not ultimo:
        if any(str(c.get("estado") or "") in _EMAIL_GOOD_AGG for c in contatos):
            return EngajamentoCanalAgregado.ATIVO
        return EngajamentoCanalAgregado.EM_ANALISE
    st = estado_granular_email(contatos, ultimo)
    if st in _EMAIL_GOOD_AGG:
        return EngajamentoCanalAgregado.ATIVO
    if st == EngajamentoEmailEstado.EMAIL_SWEEP_LEMBRETE_SMS.value:
        return EngajamentoCanalAgregado.INATIVO
    if st in _EMAIL_TERMINAL_INATIVO:
        return (
            EngajamentoCanalAgregado.EM_ANALISE
            if algum_email_disponivel_para_envio(contatos)
            else EngajamentoCanalAgregado.INATIVO
        )
    if st in _EMAIL_PENDING_AGG:
        return EngajamentoCanalAgregado.EM_ANALISE
    return EngajamentoCanalAgregado.EM_ANALISE


def rollup_engajamento_sms(
    contatos: list[dict[str, Any]],
    ultimo_envio_endereco: str | None,
) -> EngajamentoCanalAgregado:
    if not contatos:
        return EngajamentoCanalAgregado.INATIVO
    if not algum_sms_ainda_tentavel(contatos):
        return EngajamentoCanalAgregado.INATIVO
    ultimo = normalizar_telefone(ultimo_envio_endereco or "")
    if not ultimo:
        if any(str(c.get("estado") or "") in _SMS_GOOD_AGG for c in contatos):
            return EngajamentoCanalAgregado.ATIVO
        return EngajamentoCanalAgregado.EM_ANALISE
    st = estado_granular_sms(contatos, ultimo)
    if st in _SMS_GOOD_AGG:
        return EngajamentoCanalAgregado.ATIVO
    if st in _SMS_TERMINAL_INATIVO:
        return (
            EngajamentoCanalAgregado.EM_ANALISE
            if algum_sms_disponivel_para_envio(contatos)
            else EngajamentoCanalAgregado.INATIVO
        )
    if st in _SMS_PENDING_AGG:
        return EngajamentoCanalAgregado.EM_ANALISE
    return EngajamentoCanalAgregado.EM_ANALISE


def contatos_iniciais_email(enderecos: list[str], *, now_iso: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for e in enderecos:
        n = normalizar_email(e)
        if not n or n in seen:
            continue
        seen.add(n)
        out.append(
            {
                "endereco": n,
                "estado": EngajamentoEmailEstado.ATIVO.value,
                "ultima_atualizacao_em": now_iso,
            }
        )
    return out


def escolher_email_efetivo(contatos: list[dict[str, Any]], preferencia: str | None) -> str | None:
    """Ordenação: preferência da requisição se utilizável; senão primeiro contato não bloqueado."""
    if preferencia:
        p = normalizar_email(preferencia)
        if p:
            presente = any(normalizar_email(str(c.get("endereco") or "")) == p for c in contatos)
            if not presente:
                return p
            st = estado_granular_email(contatos, p)
            if not email_granular_bloqueia_notificacao(st):
                return p
    for c in contatos:
        end = normalizar_email(str(c.get("endereco") or ""))
        if not end:
            continue
        st = str(c.get("estado") or "")
        if not email_granular_bloqueia_notificacao(st):
            return end
    return None


def escolher_telefone_efetivo(contatos: list[dict[str, Any]], preferencia: str | None) -> str | None:
    if preferencia:
        p = normalizar_telefone(preferencia)
        if p:
            presente = any(normalizar_telefone(str(c.get("endereco") or "")) == p for c in contatos)
            if not presente:
                return p
            st = estado_granular_sms(contatos, p)
            if not sms_granular_bloqueia_notificacao(st):
                return p
    for c in contatos:
        end = normalizar_telefone(str(c.get("endereco") or ""))
        if not end:
            continue
        st = str(c.get("estado") or "")
        if not sms_granular_bloqueia_notificacao(st):
            return end
    return None


def escolher_email_prior_novos_engajamento(
    contatos_antes: list[dict[str, Any]],
    contatos_depois: list[dict[str, Any]],
    candidatos_payload: tuple[str, ...],
) -> str | None:
    """Primeiro e-mail do payload que ainda não existia no engajamento; senão ``escolher_email_efetivo``."""
    for e in candidatos_payload:
        n = normalizar_email(e)
        if not n:
            continue
        if not contatos_incluem_email(contatos_antes, n):
            return n
    pref = candidatos_payload[0] if candidatos_payload else None
    return escolher_email_efetivo(contatos_depois, pref)


def escolher_telefone_prior_novos_engajamento(
    contatos_antes: list[dict[str, Any]],
    contatos_depois: list[dict[str, Any]],
    candidatos_payload: tuple[str, ...],
) -> str | None:
    for t in candidatos_payload:
        n = normalizar_telefone(t)
        if not n:
            continue
        if not contatos_incluem_telefone(contatos_antes, n):
            return n
    pref = candidatos_payload[0] if candidatos_payload else None
    return escolher_telefone_efetivo(contatos_depois, pref)


def proximo_email_tentavel_apos_contato(
    contatos: list[dict[str, Any]],
    email_atual: str | None,
) -> str | None:
    """Próximo e-mail não bloqueado na ordem da lista, após ``email_atual`` (normalizado)."""
    cur = normalizar_email(email_atual or "")
    idx = -1
    if cur:
        for i, c in enumerate(contatos):
            if normalizar_email(str(c.get("endereco") or "")) == cur:
                idx = i
                break
    for j in range(idx + 1, len(contatos)):
        c = contatos[j]
        end = normalizar_email(str(c.get("endereco") or ""))
        if not end:
            continue
        st = str(c.get("estado") or "")
        if not email_granular_bloqueia_notificacao(st):
            return end
    return None


def proximo_telefone_tentavel_apos_contato(
    contatos: list[dict[str, Any]],
    telefone_atual: str | None,
) -> str | None:
    """Próximo telefone não bloqueado na ordem da lista, após ``telefone_atual`` (normalizado)."""
    cur = normalizar_telefone(telefone_atual or "")
    idx = -1
    if cur:
        for i, c in enumerate(contatos):
            if normalizar_telefone(str(c.get("endereco") or "")) == cur:
                idx = i
                break
    for j in range(idx + 1, len(contatos)):
        c = contatos[j]
        end = normalizar_telefone(str(c.get("endereco") or ""))
        if not end:
            continue
        st = str(c.get("estado") or "")
        if not sms_granular_bloqueia_notificacao(st):
            return end
    return None


def contatos_iniciais_sms(enderecos: list[str], *, now_iso: str) -> list[dict[str, Any]]:
    from app.reenvio.servicos.validacao_telefone_sms_br import normalizar_telefone_movel_br_para_sms

    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for e in enderecos:
        n = normalizar_telefone_movel_br_para_sms(e)
        if not n or n in seen:
            continue
        seen.add(n)
        out.append(
            {
                "endereco": n,
                "estado": EngajamentoSmsEstado.ATIVO.value,
                "ultima_atualizacao_em": now_iso,
            }
        )
    return out
