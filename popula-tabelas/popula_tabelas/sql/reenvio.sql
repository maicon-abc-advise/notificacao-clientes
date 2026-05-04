-- Tabelas atuais de reenvio (fila SMS está no Redis). Não removemos tabelas antigas aqui.
-- Bases já criadas com coluna ``external_id``: renomear para ``id_externo`` antes de alinhar o código.
--   ALTER TABLE public.emails_enviados RENAME COLUMN external_id TO id_externo;
--   ALTER TABLE public.sms_enviados RENAME COLUMN external_id TO id_externo;
-- Engajamento por fornecedor: ver ``orquestracao_consultas_fornecedores.sql`` (``engajamento_fornecedores``).

CREATE TABLE IF NOT EXISTS public.sms_enviados (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    id_externo text NOT NULL UNIQUE,
    id_mensagem_zenvia text UNIQUE,
    telefone text NOT NULL,
    tipo_template text NOT NULL,
    contexto jsonb NOT NULL DEFAULT '{}'::jsonb,
    remetente text,
    fornecedor_id uuid,
    status_ultimo text NOT NULL DEFAULT 'processando',
    motivo_ultimo_evento text,
    tentativas_reprocessar int NOT NULL DEFAULT 0,
    proxima_tentativa_em timestamptz,
    criado_em timestamptz NOT NULL DEFAULT now(),
    atualizado_em timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT sms_enviados_status_chk CHECK (
        status_ultimo IN ('processando', 'enviado', 'lido', 'falha_definitiva', 'reprocessar')
    )
);

CREATE INDEX IF NOT EXISTS idx_sms_enviados_id_mensagem
    ON public.sms_enviados (id_mensagem_zenvia)
    WHERE id_mensagem_zenvia IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_sms_enviados_fornecedor
    ON public.sms_enviados (fornecedor_id)
    WHERE fornecedor_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.emails_enviados (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    id_externo text NOT NULL UNIQUE,
    id_mensagem_zenvia text UNIQUE,
    email_destinatario text NOT NULL,
    tipo_template text NOT NULL,
    contexto jsonb NOT NULL DEFAULT '{}'::jsonb,
    remetente text,
    telefone_sms_fallback text,
    fornecedor_id uuid,
    status_ultimo text NOT NULL DEFAULT 'processando',
    motivo_ultimo_evento text,
    tentativas_reprocessar int NOT NULL DEFAULT 0,
    proxima_tentativa_em timestamptz,
    criado_em timestamptz NOT NULL DEFAULT now(),
    atualizado_em timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT emails_enviados_status_chk CHECK (
        status_ultimo IN ('processando', 'enviado', 'lido', 'falha_definitiva', 'reprocessar')
    )
);

CREATE INDEX IF NOT EXISTS idx_emails_enviados_id_mensagem
    ON public.emails_enviados (id_mensagem_zenvia)
    WHERE id_mensagem_zenvia IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_emails_enviados_fornecedor
    ON public.emails_enviados (fornecedor_id)
    WHERE fornecedor_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.webhook_eventos_processados (
    id_evento text PRIMARY KEY,
    processado_em timestamptz NOT NULL DEFAULT now()
);
