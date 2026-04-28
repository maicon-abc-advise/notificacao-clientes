"""Reenvio: webhooks Zenvia, Redis (e-mails **esperando confirmação**; fila **sms-pendente**) e engajamento em Postgres.

- E-mails após envio (webhooks / sweep): Redis ``emails-esperando-confirmacao:*``.
- Fila SMS **a enviar**: Redis ``sms-pendente:*``.
- Registos **sms_enviados** e **emails_enviados**: criados/atualizados em **mensageria** após envio; webhooks SMS atualizam ``sms_enviados``.
- ``engajamento_usuarios``: atualizado em eventos-chave de SMS (quando há ``usuario_id``).
"""
