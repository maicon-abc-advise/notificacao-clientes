"""Rótulos e cores para o dashboard (contrato estável para o front)."""

from __future__ import annotations

from typing import Any


def _badge(rotulo: str, cor: str) -> dict[str, str]:
    return {"rotulo": rotulo, "cor": cor}


def estado_postgres_mensagem(status_ultimo: str) -> dict[str, str]:
    """Mapeia ``status_ultimo`` (incl. ``lido`` vs ``enviado``)."""
    if status_ultimo == "falha_definitiva":
        return _badge("Falha definitiva", "danger")
    if status_ultimo == "reprocessar":
        return _badge("Aguardando reenvio", "warning")
    if status_ultimo == "processando":
        return _badge("Em processamento", "info")
    if status_ultimo == "lido":
        return _badge("Lido", "success")
    if status_ultimo == "lido_maquina":
        return _badge("Aberto por máquina", "warning")
    if status_ultimo == "clicado":
        return _badge("Link clicado", "success")
    if status_ultimo == "enviado":
        return _badge("Enviado / entregue", "success")
    return _badge(status_ultimo, "neutral")


def estado_engajamento_comprador(*, converteu: bool, primeira_consulta_sem_cadastro: bool) -> dict[str, str]:
    if converteu:
        return _badge("Convertido", "success")
    if primeira_consulta_sem_cadastro:
        return _badge("Elegível — aguardando", "info")
    return _badge("Já usava plataforma", "neutral")


def enriquecer_linha_engajamento_comprador(linha: dict[str, Any]) -> dict[str, Any]:
    out = dict(linha)
    out["estado_exibicao"] = estado_engajamento_comprador(
        converteu=bool(out.get("converteu")),
        primeira_consulta_sem_cadastro=bool(out.get("primeira_consulta_sem_cadastro")),
    )
    return out


def estado_redis_email_pendente() -> dict[str, str]:
    return _badge("Na fila (pré-envio)", "neutral")


def estado_redis_email_esperando(status_atual: str | None) -> dict[str, str]:
    s = (status_atual or "").strip().upper()
    m: dict[str, tuple[str, str]] = {
        "AGUARDANDO_ABERTURA": ("Aguardando abertura", "neutral"),
        "ENVIADO_PROVEDOR": ("Enviado ao provedor", "info"),
        "ENTREGUE_CAIXA": ("Entregue na caixa", "success"),
        "AGUARDANDO_REENVIO": ("Aguardando reenvio", "warning"),
    }
    rotulo, cor = m.get(s, (status_atual or "—", "neutral"))
    return _badge(rotulo, cor)


def estado_redis_sms_pendente() -> dict[str, str]:
    return _badge("Na fila (a enviar)", "neutral")


def estado_redis_sms_esperando(status_atual: str | None) -> dict[str, str]:
    s = (status_atual or "").strip().upper()
    m: dict[str, tuple[str, str]] = {
        "AGUARDANDO_CONFIRMACAO": ("Aguardando confirmação", "neutral"),
        "ENVIADO_PROVEDOR": ("Enviado ao provedor", "info"),
        "ENTREGUE": ("Entregue", "success"),
    }
    rotulo, cor = m.get(s, (status_atual or "—", "neutral"))
    return _badge(rotulo, cor)


def enriquecer_linha_postgres(linha: dict[str, Any], *, canal: str) -> dict[str, Any]:
    out = dict(linha)
    if canal in ("email", "sms"):
        out["estado_exibicao"] = estado_postgres_mensagem(str(out.get("status_ultimo") or ""))
    return out


def enriquecer_redis_email_pendente(linha: dict[str, Any]) -> dict[str, Any]:
    out = dict(linha)
    out["estado_exibicao"] = estado_redis_email_pendente()
    return out


def enriquecer_redis_email_esperando(linha: dict[str, Any]) -> dict[str, Any]:
    out = dict(linha)
    out["estado_exibicao"] = estado_redis_email_esperando(out.get("status_atual"))
    return out


def enriquecer_redis_sms_pendente(linha: dict[str, Any]) -> dict[str, Any]:
    out = dict(linha)
    out["estado_exibicao"] = estado_redis_sms_pendente()
    return out


def enriquecer_redis_sms_esperando(linha: dict[str, Any]) -> dict[str, Any]:
    out = dict(linha)
    out["estado_exibicao"] = estado_redis_sms_esperando(out.get("status_atual"))
    return out


def estado_postgres_ligacao(status_ultimo: str) -> dict[str, str]:
    m: dict[str, tuple[str, str]] = {
        "disparado": ("Disparado", "info"),
        "tocando": ("Tocando", "info"),
        "em_andamento": ("Em andamento", "info"),
        "concluido": ("Concluído", "success"),
        "sem_resposta": ("Sem resposta", "warning"),
        "caixa_postal": ("Caixa postal", "warning"),
        "falha": ("Falha", "danger"),
        "falha_definitiva": ("Falha definitiva", "danger"),
    }
    rotulo, cor = m.get(status_ultimo, (status_ultimo or "—", "neutral"))
    return _badge(rotulo, cor)


def estado_redis_ligacao_pendente() -> dict[str, str]:
    return _badge("Na fila (a disparar)", "neutral")


def enriquecer_linha_postgres_ligacao(linha: dict[str, Any]) -> dict[str, Any]:
    out = dict(linha)
    out["estado_exibicao"] = estado_postgres_ligacao(str(out.get("status_ultimo") or ""))
    return out


def enriquecer_redis_ligacao_pendente(linha: dict[str, Any]) -> dict[str, Any]:
    out = dict(linha)
    out["estado_exibicao"] = estado_redis_ligacao_pendente()
    return out
