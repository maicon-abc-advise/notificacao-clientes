"""Leitura de variáveis: banco (prioridade) com fallback .env."""

from __future__ import annotations

import logging
from typing import Any

import asyncpg
from fastapi import HTTPException, status

from app.config.variaveis_sistema import catalogo as cat
from app.config.variaveis_sistema import repositorio as repo
from app.config.variaveis_sistema.modelo import (
    CorpoAtualizarVariavel,
    GrupoVariaveisSistema,
    OrigemVariavelSistema,
    RespostaListagemVariaveis,
    TipoVariavelSistema,
    VariavelSistemaItem,
    VariavelSistemaRegistro,
)

_log = logging.getLogger(__name__)

_cache_banco: dict[str, str] | None = None


def invalidar_cache_variaveis() -> None:
    global _cache_banco
    _cache_banco = None


async def recarregar_cache_variaveis(pool: asyncpg.Pool) -> None:
    global _cache_banco
    try:
        _cache_banco = await repo.mapa_valores(pool)
    except asyncpg.UndefinedTableError:
        _log.warning("Tabela variaveis_sistema ausente; usando apenas fallbacks .env")
        _cache_banco = {}
    except Exception:
        _log.exception("Falha ao carregar variaveis_sistema; mantendo cache anterior")
        if _cache_banco is None:
            _cache_banco = {}


def obter_valor_bruto(chave: str) -> str:
    """Valor efetivo: banco > .env."""
    chave = chave.strip()
    if _cache_banco is not None and chave in _cache_banco:
        return _cache_banco[chave]
    return cat.valor_fallback_env(chave)


def obter_str(chave: str) -> str:
    return obter_valor_bruto(chave).strip()


def obter_int(chave: str) -> int:
    return int(_parse_valor_typed(chave, TipoVariavelSistema.INT))


def obter_float(chave: str) -> float:
    tipo = cat.CATALOGO[chave].tipo
    if tipo == TipoVariavelSistema.PERCENT:
        return float(_parse_valor_typed(chave, TipoVariavelSistema.PERCENT))
    return float(_parse_valor_typed(chave, TipoVariavelSistema.FLOAT))


def obter_bool(chave: str) -> bool:
    bruto = obter_valor_bruto(chave).strip().lower()
    if bruto in ("1", "true", "yes", "on", "sim"):
        return True
    if bruto in ("0", "false", "no", "off", "nao", "não", ""):
        return False
    raise ValueError(f"Valor booleano inválido para {chave!r}: {bruto!r}")


def _parse_valor_typed(chave: str, tipo: TipoVariavelSistema) -> Any:
    bruto = obter_valor_bruto(chave).strip()
    try:
        if tipo in (TipoVariavelSistema.INT, TipoVariavelSistema.PERCENT):
            if "." in bruto:
                return int(float(bruto))
            return int(bruto)
        if tipo == TipoVariavelSistema.FLOAT:
            return float(bruto)
        if tipo == TipoVariavelSistema.BOOL:
            return obter_bool(chave)
        return bruto
    except ValueError as e:
        raise ValueError(f"Valor inválido para {chave!r} (tipo {tipo.value}): {bruto!r}") from e


def _item_de_registro(reg: VariavelSistemaRegistro, origem: OrigemVariavelSistema) -> VariavelSistemaItem:
    valor_efetivo = reg.valor if origem == OrigemVariavelSistema.BANCO else cat.valor_fallback_env(reg.chave)
    return VariavelSistemaItem(
        chave=reg.chave,
        valor=reg.valor,
        tipo=reg.tipo,
        grupo=reg.grupo,
        descricao=reg.descricao,
        editavel=reg.editavel,
        origem=origem,
        valor_efetivo=valor_efetivo,
    )


async def listar_para_dashboard(pool: asyncpg.Pool) -> RespostaListagemVariaveis:
    try:
        do_banco = {r.chave: r for r in await repo.listar_todas(pool)}
    except asyncpg.UndefinedTableError:
        do_banco = {}

    itens: list[VariavelSistemaItem] = []
    for chave, meta in cat.CATALOGO.items():
        if chave in do_banco:
            itens.append(_item_de_registro(do_banco[chave], OrigemVariavelSistema.BANCO))
        else:
            fb = cat.valor_fallback_env(chave)
            itens.append(
                VariavelSistemaItem(
                    chave=chave,
                    valor=fb,
                    tipo=meta.tipo,
                    grupo=meta.grupo,
                    descricao=meta.descricao,
                    editavel=meta.editavel,
                    origem=OrigemVariavelSistema.ENV,
                    valor_efetivo=fb,
                )
            )

    por_grupo: dict[str, list[VariavelSistemaItem]] = {}
    for item in itens:
        por_grupo.setdefault(item.grupo, []).append(item)

    ordem = list(cat.ROTULOS_GRUPO.keys())
    grupos: list[GrupoVariaveisSistema] = []
    for nome in ordem:
        vars_grupo = por_grupo.pop(nome, [])
        if not vars_grupo:
            continue
        grupos.append(
            GrupoVariaveisSistema(
                nome=nome,
                rotulo=cat.ROTULOS_GRUPO.get(nome, nome),
                variaveis=sorted(vars_grupo, key=lambda v: v.chave),
            )
        )
    for nome, vars_grupo in sorted(por_grupo.items()):
        grupos.append(
            GrupoVariaveisSistema(
                nome=nome,
                rotulo=cat.ROTULOS_GRUPO.get(nome, nome),
                variaveis=sorted(vars_grupo, key=lambda v: v.chave),
            )
        )
    return RespostaListagemVariaveis(grupos=grupos)


def _validar_valor_para_tipo(valor: str, tipo: TipoVariavelSistema) -> str:
    bruto = valor.strip()
    if tipo == TipoVariavelSistema.STRING:
        return valor
    if tipo == TipoVariavelSistema.BOOL:
        norm = bruto.lower()
        if norm in ("1", "true", "yes", "on", "sim"):
            return "true"
        if norm in ("0", "false", "no", "off", "nao", "não"):
            return "false"
        raise ValueError("Use true/false")
    if tipo in (TipoVariavelSistema.INT, TipoVariavelSistema.PERCENT):
        n = int(float(bruto))
        if tipo == TipoVariavelSistema.PERCENT and not (0 <= n <= 100):
            raise ValueError("Percentual deve estar entre 0 e 100")
        if tipo == TipoVariavelSistema.INT and n < 0:
            raise ValueError("Inteiro deve ser >= 0")
        return str(n)
    if tipo == TipoVariavelSistema.FLOAT:
        return str(float(bruto))
    return valor


def _validar_pct_comprador(cache_apos: dict[str, str]) -> None:
    total = 0.0
    for chave in cat.CHAVES_PCT_COMPRADOR:
        bruto = cache_apos.get(chave)
        if bruto is None:
            bruto = cat.valor_fallback_env(chave)
        total += float(bruto)
    if abs(total - 100.0) > 0.001:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Percentuais do comprador devem somar 100 (atual: {total:g}).",
        )


async def atualizar_variavel(
    pool: asyncpg.Pool,
    chave: str,
    corpo: CorpoAtualizarVariavel,
) -> VariavelSistemaItem:
    chave = chave.strip()
    meta = cat.CATALOGO.get(chave)
    if meta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Variável desconhecida: {chave}")

    registro = await repo.buscar_por_chave(pool, chave)
    if registro is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Variável {chave!r} não existe no banco. Rode o seed no Supabase.",
        )
    if not registro.editavel:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Variável não editável.")

    try:
        valor_normalizado = _validar_valor_para_tipo(corpo.valor, registro.tipo)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    atualizado = await repo.atualizar_valor(pool, chave, valor_normalizado)
    if atualizado is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variável não encontrada.")

    await recarregar_cache_variaveis(pool)

    if chave in cat.CHAVES_PCT_COMPRADOR:
        cache_atual = dict(_cache_banco or {})
        _validar_pct_comprador(cache_atual)

    return _item_de_registro(atualizado, OrigemVariavelSistema.BANCO)
