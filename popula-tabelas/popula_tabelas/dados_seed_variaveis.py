"""Seed de variáveis de sistema (defaults alinhados ao .env / config.py)."""

from __future__ import annotations


def linhas_seed_variaveis() -> tuple[tuple[str, str, str, str, str, bool], ...]:
    return (
        ("comprador_pct_sms", "100", "percent", "comprador", "% de envios por SMS quando canal omitido no /enviar", True),
        ("comprador_pct_rcs", "0", "percent", "comprador", "% de envios por RCS (futuro)", True),
        ("comprador_pct_whatsapp", "0", "percent", "comprador", "% de envios por WhatsApp (futuro)", True),
        ("sweep_esperando_confirmacao_dias", "2", "int", "mensagens", "Dias no Redis aguardando confirmação pós-envio", True),
        ("reenvio_sms_reprocessar_max", "10", "int", "mensagens", "Máximo de reprocessamentos SMS (fornecedor)", True),
        ("url_plataforma", "https://buscafornecedor.com.br", "string", "urls", "URL base da plataforma (templates email/SMS)", True),
        ("url_login", "https://buscafornecedor.com.br/creditos", "string", "urls", "URL de login/área logada nos templates", True),
        ("url_landing_info_consulta", "https://buscafornecedor.com.br/info-consulta", "string", "urls", "Landing após clique em link rastreado", True),
        ("routine_min_buscas", "5", "int", "whatsapp", "Mín. aparições em buscas para entrar na fila WhatsApp", True),
        ("routine_min_buscas_primeira_entrada", "1", "int", "whatsapp", "Mín. aparições na primeira entrada na fila", True),
        ("routine_max_falhas", "3", "int", "whatsapp", "Máx. falhas antes de desistir do contato", True),
        ("routine_cooldown_hours", "48", "int", "whatsapp", "Horas de cooldown entre tentativas", True),
        ("whatsapp_validacao_cache_dias", "30", "int", "whatsapp", "Dias de cache da validação de número WhatsApp", True),
        ("openai_model", "gpt-4o-mini", "string", "whatsapp", "Modelo OpenAI do agente WhatsApp (Cláudia)", True),
        ("limiar_creditos_no_fim", "5", "int", "creditos", "Alerta quando créditos estão acabando", True),
        ("creditos_lembrete_cadencia_dias", "7", "int", "creditos", "Dias entre lembretes de crédito", True),
        ("growthbook_enabled", "false", "bool", "experimentos", "Liga/desliga teste A/B de template de email", True),
        ("growthbook_feature_key", "email-apareceu-busca-template-teste", "string", "experimentos", "Chave da feature no GrowthBook", True),
        ("growthbook_experimento_id", "email-apareceu-busca-variacao-teste", "string", "experimentos", "ID do experimento (label interno)", True),
    )
