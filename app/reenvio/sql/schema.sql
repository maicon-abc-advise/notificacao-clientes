-- Tabelas atuais de reenvio (fila SMS está no Redis). Não removemos tabelas antigas aqui.

CREATE TABLE IF NOT EXISTS public.engajamento_usuarios (
    usuario_id uuid PRIMARY KEY,
    engajamento_estado text NOT NULL DEFAULT 'ativo',
    engajamento_atualizado_em timestamptz NOT NULL DEFAULT now(),
    ultimo_lembrete_limite_semanal_em timestamptz,
    recebe_email boolean NOT NULL DEFAULT true,
    aparicoes_mes int NOT NULL DEFAULT 0,
    aparicoes_mes_referencia varchar(7) NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS public.sms_enviados (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    external_id text NOT NULL UNIQUE,
    id_mensagem_zenvia text UNIQUE,
    telefone text NOT NULL,
    tipo_template text NOT NULL,
    contexto jsonb NOT NULL DEFAULT '{}'::jsonb,
    remetente text,
    usuario_id uuid,
    status_ultimo text NOT NULL DEFAULT 'processando',
    motivo_ultimo_evento text,
    tentativas_reprocessar int NOT NULL DEFAULT 0,
    proxima_tentativa_em timestamptz,
    criado_em timestamptz NOT NULL DEFAULT now(),
    atualizado_em timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT sms_enviados_status_chk CHECK (
        status_ultimo IN ('processando', 'enviado', 'falha_definitiva', 'reprocessar')
    )
);

CREATE INDEX IF NOT EXISTS idx_sms_enviados_id_mensagem
    ON public.sms_enviados (id_mensagem_zenvia)
    WHERE id_mensagem_zenvia IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_sms_enviados_usuario
    ON public.sms_enviados (usuario_id)
    WHERE usuario_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.emails_enviados (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    external_id text NOT NULL UNIQUE,
    id_mensagem_zenvia text UNIQUE,
    email_destinatario text NOT NULL,
    tipo_template text NOT NULL,
    contexto jsonb NOT NULL DEFAULT '{}'::jsonb,
    remetente text,
    telefone_sms_fallback text,
    usuario_id uuid,
    status_ultimo text NOT NULL DEFAULT 'processando',
    motivo_ultimo_evento text,
    tentativas_reprocessar int NOT NULL DEFAULT 0,
    proxima_tentativa_em timestamptz,
    criado_em timestamptz NOT NULL DEFAULT now(),
    atualizado_em timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT emails_enviados_status_chk CHECK (
        status_ultimo IN ('processando', 'enviado', 'falha_definitiva', 'reprocessar')
    )
);

CREATE INDEX IF NOT EXISTS idx_emails_enviados_id_mensagem
    ON public.emails_enviados (id_mensagem_zenvia)
    WHERE id_mensagem_zenvia IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_emails_enviados_usuario
    ON public.emails_enviados (usuario_id)
    WHERE usuario_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.webhook_eventos_processados (
    id_evento text PRIMARY KEY,
    processado_em timestamptz NOT NULL DEFAULT now()
);
