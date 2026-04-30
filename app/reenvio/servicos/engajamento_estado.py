from __future__ import annotations
import enum
from app.reenvio.servicos.classificar_cause_email import ResultadoClassificacaoEmail

class EngajamentoEmailEstado(enum.StrEnum):
    ATIVO = "ativo"
    EMAIL_ENVIADO_API = "email_enviado_api"
    EMAIL_LIDO = "email_lido"
    EMAIL_WEBHOOK_SENT = "email_webhook_sent"
    EMAIL_ENTREGUE_CAIXA = "email_entregue_caixa"
    EMAIL_BOUNCE_HARD_SEM_SMS = "email_bounce_hard_sem_sms"
    EMAIL_BOUNCE_HARD_SMS_FILA = "email_bounce_hard_sms_fila"
    EMAIL_FALHA_RECUPERAVEL_MAILBOX_FULL = "email_falha_recuperavel_mailbox_full"
    EMAIL_FALHA_RECUPERAVEL_TEMPORARY = "email_falha_recuperavel_temporary"
    EMAIL_FALHA_RECUPERAVEL_UNKNOWN = "email_falha_recuperavel_unknown"
    EMAIL_SWEEP_LEMBRETE_SMS = "email_sweep_lembrete_sms"

class EngajamentoSmsEstado(enum.StrEnum):
    ATIVO = "ativo"
    SMS_ENVIADO_API = "sms_enviado_api"
    SMS_ENTREGUE = "sms_entregue"
    SMS_WEBHOOK_SENT = "sms_webhook_sent"
    SMS_FALHA_NUMERO = "sms_falha_numero"
    SMS_FALHA_LIMITE = "sms_falha_limite"
    SMS_REPROCESSAR_FILA = "sms_reprocessar_fila"

def engajamento_falha_recuperavel_email(cls: ResultadoClassificacaoEmail) -> EngajamentoEmailEstado:
    m: dict[ResultadoClassificacaoEmail, EngajamentoEmailEstado] = {
        ResultadoClassificacaoEmail.MAILBOX_FULL: EngajamentoEmailEstado.EMAIL_FALHA_RECUPERAVEL_MAILBOX_FULL,
        ResultadoClassificacaoEmail.TEMPORARY: EngajamentoEmailEstado.EMAIL_FALHA_RECUPERAVEL_TEMPORARY,
        ResultadoClassificacaoEmail.UNKNOWN: EngajamentoEmailEstado.EMAIL_FALHA_RECUPERAVEL_UNKNOWN,
    }
    try:
        return m[cls]
    except KeyError as e:
        msg = f"classificação não é falha recuperável de e-mail: {cls!r}"
        raise ValueError(msg) from e
