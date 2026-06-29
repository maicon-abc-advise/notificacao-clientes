"""Integração GrowthBook para sorteio de variante de e-mail de busca."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.config.config import obter_configuracao
from app.experimentos.variante_email import VARIANTE_PADRAO, normalizar_variante
from app.templates.modelo import CodigoTipoTemplate

if TYPE_CHECKING:
    from growthbook import GrowthBookClient

_log = logging.getLogger(__name__)

_TIPOS_EMAIL_BUSCA = frozenset(
    {
        CodigoTipoTemplate.APARECEU_BUSCA,
        CodigoTipoTemplate.APARECEU_BUSCA_SEM_REGISTRO,
    }
)

_client: GrowthBookClient | None = None
_inicializado = False


async def iniciar_growthbook() -> None:
    global _client, _inicializado
    cfg = obter_configuracao()
    if not cfg.growthbook_enabled:
        _log.info("GrowthBook desligado (GROWTHBOOK_ENABLED=false)")
        _inicializado = True
        return
    if not cfg.growthbook_client_key:
        _log.warning("GrowthBook ligado sem GROWTHBOOK_CLIENT_KEY; sorteio ignorado")
        _inicializado = True
        return
    try:
        from growthbook import GrowthBookClient, Options

        _client = GrowthBookClient(
            Options(
                api_host="https://cdn.growthbook.io",
                client_key=cfg.growthbook_client_key,
            )
        )
        ok = await _client.initialize()
        if not ok:
            _log.warning("GrowthBook initialize() retornou false")
            await _client.close()
            _client = None
        else:
            _log.info("GrowthBook client inicializado")
    except Exception:
        _log.exception("Falha ao inicializar GrowthBook")
        _client = None
    _inicializado = True


async def encerrar_growthbook() -> None:
    global _client, _inicializado
    if _client is not None:
        try:
            await _client.close()
        except Exception:
            _log.exception("Falha ao encerrar GrowthBook client")
    _client = None
    _inicializado = False


async def resolver_variante_email_busca(
    cnpj_basico: str | None,
    *,
    tipo_template: CodigoTipoTemplate,
) -> tuple[str, str | None]:
    """Retorna (variante, experimento_id). Com GrowthBook off, sempre (simples, None)."""
    if tipo_template not in _TIPOS_EMAIL_BUSCA:
        return VARIANTE_PADRAO, None

    cfg = obter_configuracao()
    if not cfg.growthbook_enabled:
        return VARIANTE_PADRAO, None

    cnpj = (cnpj_basico or "").strip()
    if len(cnpj) != 8:
        return VARIANTE_PADRAO, None

    if _client is None:
        _log.warning("GrowthBook sem client; variante=%s cnpj=%s", VARIANTE_PADRAO, cnpj)
        return VARIANTE_PADRAO, None

    try:
        from growthbook import UserContext

        user = UserContext(attributes={"id": cnpj})
        bruto = await _client.get_feature_value(
            cfg.growthbook_feature_key,
            VARIANTE_PADRAO,
            user,
        )
        variante = normalizar_variante(str(bruto) if bruto is not None else None)
        exp_id = (cfg.growthbook_experimento_id or "").strip() or None
        _log.info(
            "GrowthBook variante=%s experimento_id=%s cnpj=%s feature=%s",
            variante,
            exp_id,
            cnpj,
            cfg.growthbook_feature_key,
        )
        return variante, exp_id
    except Exception:
        _log.exception("GrowthBook resolver falhou cnpj=%s", cnpj)
        return VARIANTE_PADRAO, None
