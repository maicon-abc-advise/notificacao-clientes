"""Reenvio: webhooks Zenvia, Redis (e-mails e SMS **pendentes**) e engajamento em Postgres.

- Fila SMS **a enviar**: Redis (`sms:pendente:*`).
- Registos **sms_enviados** e **emails_enviados**: criados/atualizados em **mensageria** após envio; webhooks SMS atualizam ``sms_enviados``.
- ``engajamento_usuarios``: atualizado em eventos-chave de SMS (quando há ``usuario_id``).
"""
