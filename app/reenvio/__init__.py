"""Reenvio: webhooks Zenvia, Redis (e-mails **esperando confirmação**; fila **sms-pendente**) e engajamento em Postgres.

- E-mails após envio (webhooks / sweep): Redis ``emails-esperando-confirmacao:*``.
- Fila SMS **a enviar**: Redis ``sms-pendente:*``.
- Registos **sms_enviados** e **emails_enviados**: criados/atualizados em **mensageria** após envio; webhooks SMS atualizam ``sms_enviados``.
- ``engajamento_fornecedores``: agregados ``engajamento_email`` / ``engajamento_sms`` (``ativo`` | ``em_analise`` | ``inativo``), listas ``contatos_email`` / ``contatos_sms`` (jsonb) e últimos envios por canal.
"""
