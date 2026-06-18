-- Fila/funil WhatsApp (substitui dash_contato_fornecedor no fluxo notificacao-clientes).

CREATE TABLE IF NOT EXISTS public.whatsapp_envios (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cnpj_basico text NOT NULL,
    numero_telefone text NOT NULL,
    fornecedor_id uuid,
    status text NOT NULL DEFAULT 'pendente',
    whatsapp_status text NOT NULL DEFAULT 'nao_verificado',
    etapa1 timestamptz,
    etapa2 timestamptz,
    etapa3 timestamptz,
    motivo_falha text,
    criado_em timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT whatsapp_envios_cnpj_telefone_uniq UNIQUE (cnpj_basico, numero_telefone),
    CONSTRAINT whatsapp_envios_status_chk CHECK (
        status IN ('pendente', 'contatado', 'concluido_sucesso', 'concluido_falha')
    ),
    CONSTRAINT whatsapp_envios_whatsapp_status_chk CHECK (
        whatsapp_status IN ('nao_verificado', 'valido', 'invalido')
    )
);

CREATE INDEX IF NOT EXISTS idx_whatsapp_envios_status
    ON public.whatsapp_envios (status);

CREATE INDEX IF NOT EXISTS idx_whatsapp_envios_cnpj
    ON public.whatsapp_envios (cnpj_basico);

CREATE INDEX IF NOT EXISTS idx_whatsapp_envios_telefone
    ON public.whatsapp_envios (numero_telefone);

CREATE TABLE IF NOT EXISTS public.whatsapp_rotina_execucoes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    resultado jsonb NOT NULL DEFAULT '{}'::jsonb,
    iniciado_em timestamptz NOT NULL,
    finalizado_em timestamptz NOT NULL,
    criado_em timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_whatsapp_rotina_execucoes_iniciado
    ON public.whatsapp_rotina_execucoes (iniciado_em DESC);
