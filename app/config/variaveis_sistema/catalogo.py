"""Metadados e fallbacks .env das variáveis de sistema."""

from __future__ import annotations

from app.config.config import Configuracao, obter_configuracao
from app.config.variaveis_sistema.modelo import TipoVariavelSistema, VariavelSistemaRegistro

CHAVES_PCT_COMPRADOR: frozenset[str] = frozenset(
    {
        "comprador_pct_sms",
        "comprador_pct_rcs",
        "comprador_pct_whatsapp",
    }
)

ROTULOS_GRUPO: dict[str, str] = {
    "comprador": "Comprador (busca)",
    "mensagens": "Mensagens & reenvio",
    "urls": "URLs",
    "whatsapp": "WhatsApp",
    "creditos": "Créditos",
    "experimentos": "Experimentos",
}

CATALOGO: dict[str, VariavelSistemaRegistro] = {
    "comprador_pct_sms": VariavelSistemaRegistro(
        chave="comprador_pct_sms",
        valor="100",
        tipo=TipoVariavelSistema.PERCENT,
        grupo="comprador",
        descricao="% de envios por SMS quando canal omitido no /enviar",
    ),
    "comprador_pct_rcs": VariavelSistemaRegistro(
        chave="comprador_pct_rcs",
        valor="0",
        tipo=TipoVariavelSistema.PERCENT,
        grupo="comprador",
        descricao="% de envios por RCS (futuro)",
    ),
    "comprador_pct_whatsapp": VariavelSistemaRegistro(
        chave="comprador_pct_whatsapp",
        valor="0",
        tipo=TipoVariavelSistema.PERCENT,
        grupo="comprador",
        descricao="% de envios por WhatsApp (futuro)",
    ),
    "sweep_esperando_confirmacao_dias": VariavelSistemaRegistro(
        chave="sweep_esperando_confirmacao_dias",
        valor="2",
        tipo=TipoVariavelSistema.INT,
        grupo="mensagens",
        descricao="Dias no Redis aguardando confirmação pós-envio",
    ),
    "reenvio_sms_reprocessar_max": VariavelSistemaRegistro(
        chave="reenvio_sms_reprocessar_max",
        valor="10",
        tipo=TipoVariavelSistema.INT,
        grupo="mensagens",
        descricao="Máximo de reprocessamentos SMS (fornecedor)",
    ),
    "url_plataforma": VariavelSistemaRegistro(
        chave="url_plataforma",
        valor="https://buscafornecedor.com.br",
        tipo=TipoVariavelSistema.STRING,
        grupo="urls",
        descricao="URL base da plataforma (templates email/SMS)",
    ),
    "url_login": VariavelSistemaRegistro(
        chave="url_login",
        valor="https://buscafornecedor.com.br/creditos",
        tipo=TipoVariavelSistema.STRING,
        grupo="urls",
        descricao="URL de login/área logada nos templates",
    ),
    "url_landing_info_consulta": VariavelSistemaRegistro(
        chave="url_landing_info_consulta",
        valor="https://buscafornecedor.com.br/info-consulta",
        tipo=TipoVariavelSistema.STRING,
        grupo="urls",
        descricao="Landing após clique em link rastreado",
    ),
    "routine_min_buscas": VariavelSistemaRegistro(
        chave="routine_min_buscas",
        valor="5",
        tipo=TipoVariavelSistema.INT,
        grupo="whatsapp",
        descricao="Mín. aparições em buscas para entrar na fila WhatsApp",
    ),
    "routine_min_buscas_primeira_entrada": VariavelSistemaRegistro(
        chave="routine_min_buscas_primeira_entrada",
        valor="1",
        tipo=TipoVariavelSistema.INT,
        grupo="whatsapp",
        descricao="Mín. aparições na primeira entrada na fila",
    ),
    "routine_max_falhas": VariavelSistemaRegistro(
        chave="routine_max_falhas",
        valor="3",
        tipo=TipoVariavelSistema.INT,
        grupo="whatsapp",
        descricao="Máx. falhas antes de desistir do contato",
    ),
    "routine_cooldown_hours": VariavelSistemaRegistro(
        chave="routine_cooldown_hours",
        valor="48",
        tipo=TipoVariavelSistema.INT,
        grupo="whatsapp",
        descricao="Horas de cooldown entre tentativas",
    ),
    "whatsapp_validacao_cache_dias": VariavelSistemaRegistro(
        chave="whatsapp_validacao_cache_dias",
        valor="30",
        tipo=TipoVariavelSistema.INT,
        grupo="whatsapp",
        descricao="Dias de cache da validação de número WhatsApp",
    ),
    "openai_model": VariavelSistemaRegistro(
        chave="openai_model",
        valor="gpt-4o-mini",
        tipo=TipoVariavelSistema.STRING,
        grupo="whatsapp",
        descricao="Modelo OpenAI do agente WhatsApp (Cláudia)",
    ),
    "limiar_creditos_no_fim": VariavelSistemaRegistro(
        chave="limiar_creditos_no_fim",
        valor="5",
        tipo=TipoVariavelSistema.INT,
        grupo="creditos",
        descricao="Alerta quando créditos estão acabando",
    ),
    "creditos_lembrete_cadencia_dias": VariavelSistemaRegistro(
        chave="creditos_lembrete_cadencia_dias",
        valor="7",
        tipo=TipoVariavelSistema.INT,
        grupo="creditos",
        descricao="Dias entre lembretes de crédito",
    ),
    "growthbook_enabled": VariavelSistemaRegistro(
        chave="growthbook_enabled",
        valor="false",
        tipo=TipoVariavelSistema.BOOL,
        grupo="experimentos",
        descricao="Liga/desliga teste A/B de template de email",
    ),
    "growthbook_feature_key": VariavelSistemaRegistro(
        chave="growthbook_feature_key",
        valor="email-apareceu-busca-template-teste",
        tipo=TipoVariavelSistema.STRING,
        grupo="experimentos",
        descricao="Chave da feature no GrowthBook",
    ),
    "growthbook_experimento_id": VariavelSistemaRegistro(
        chave="growthbook_experimento_id",
        valor="email-apareceu-busca-variacao-teste",
        tipo=TipoVariavelSistema.STRING,
        grupo="experimentos",
        descricao="ID do experimento (label interno)",
    ),
}


def valor_fallback_env(chave: str, cfg: Configuracao | None = None) -> str:
    """Valor padrão quando a chave não está no banco (espelha .env / config.py)."""
    c = cfg or obter_configuracao()
    meta = CATALOGO.get(chave)
    if meta is None:
        raise KeyError(chave)

    match chave:
        case "comprador_pct_sms" | "comprador_pct_rcs" | "comprador_pct_whatsapp":
            return meta.valor
        case "sweep_esperando_confirmacao_dias":
            return str(c.sweep_emails_esperando_confirmacao_dias)
        case "reenvio_sms_reprocessar_max":
            return str(c.reenvio_sms_reprocessar_max)
        case "url_plataforma":
            return c.url_plataforma_sms
        case "url_login":
            return c.url_login_sms
        case "url_landing_info_consulta":
            return c.url_landing_info_consulta
        case "routine_min_buscas":
            return str(c.routine_min_buscas)
        case "routine_min_buscas_primeira_entrada":
            return str(c.routine_min_buscas_primeira_entrada)
        case "routine_max_falhas":
            return str(c.routine_max_falhas)
        case "routine_cooldown_hours":
            return str(c.routine_cooldown_hours)
        case "whatsapp_validacao_cache_dias":
            return str(c.whatsapp_validacao_cache_dias)
        case "openai_model":
            return c.openai_model
        case "limiar_creditos_no_fim":
            return str(c.limiar_creditos_no_fim)
        case "creditos_lembrete_cadencia_dias":
            return "7"
        case "growthbook_enabled":
            return "true" if c.growthbook_enabled else "false"
        case "growthbook_feature_key":
            return c.growthbook_feature_key
        case "growthbook_experimento_id":
            return c.growthbook_experimento_id
        case _:
            return meta.valor
