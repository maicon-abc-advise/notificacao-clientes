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
    cnpj_basico text,
    status_ultimo text NOT NULL DEFAULT 'processando',
    motivo_ultimo_evento text,
    tentativas_reprocessar int NOT NULL DEFAULT 0,
    proxima_tentativa_em timestamptz,
    criado_em timestamptz NOT NULL DEFAULT now(),
    atualizado_em timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT sms_enviados_status_chk CHECK (
        status_ultimo IN ('processando', 'enviado', 'lido', 'clicado', 'falha_definitiva', 'reprocessar')
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
    fornecedor_id uuid,
    cnpj_basico text,
    status_ultimo text NOT NULL DEFAULT 'processando',
    motivo_ultimo_evento text,
    tentativas_reprocessar int NOT NULL DEFAULT 0,
    proxima_tentativa_em timestamptz,
    criado_em timestamptz NOT NULL DEFAULT now(),
    atualizado_em timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT emails_enviados_status_chk CHECK (
        status_ultimo IN ('processando', 'enviado', 'lido', 'lido_maquina', 'clicado', 'falha_definitiva', 'reprocessar')
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

CREATE TABLE IF NOT EXISTS public.ligacoes_enviadas (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    id_externo text NOT NULL UNIQUE,
    id_chamada_vapi text UNIQUE,

    telefone text NOT NULL,
    cnpj_basico text,
    fornecedor_id uuid,
    quantidade_buscas int,
    uf_buscada text,
    segmento_buscado text,

    status_ultimo text NOT NULL DEFAULT 'disparado',
    motivo_encerramento text,
    transcricao text,
    url_gravacao text,
    duracao_segundos int,
    iniciado_em timestamptz,
    encerrado_em timestamptz,

    nota_satisfacao int,
    vai_cadastrar boolean,
    analise_json jsonb NOT NULL DEFAULT '{}'::jsonb,

    criado_em timestamptz NOT NULL DEFAULT now(),
    atualizado_em timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT ligacoes_enviadas_status_chk CHECK (
        status_ultimo IN (
            'disparado', 'tocando', 'em_andamento',
            'concluido', 'sem_resposta', 'caixa_postal',
            'falha', 'falha_definitiva'
        )
    ),
    CONSTRAINT ligacoes_enviadas_satisfacao_chk CHECK (
        nota_satisfacao IS NULL OR (nota_satisfacao >= 0 AND nota_satisfacao <= 5)
    )
);

CREATE INDEX IF NOT EXISTS idx_ligacoes_enviadas_id_chamada_vapi
    ON public.ligacoes_enviadas (id_chamada_vapi)
    WHERE id_chamada_vapi IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_ligacoes_enviadas_cnpj
    ON public.ligacoes_enviadas (cnpj_basico);
