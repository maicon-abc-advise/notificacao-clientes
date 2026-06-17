-- Tabela de engajamento por telefone e canal (sms / whatsapp / ligacao).

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_type WHERE typname = 'canal_telefone_engajamento'
    ) THEN
        CREATE TYPE public.canal_telefone_engajamento AS ENUM (
            'sms',
            'whatsapp',
            'ligacao'
        );
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS public.telefone_engajamento (
    cnpj_basico   text                              NOT NULL,
    telefone      text                              NOT NULL,
    canal         public.canal_telefone_engajamento NOT NULL,
    status        text                              NOT NULL DEFAULT 'ativo',
    atualizado_em timestamptz                       NOT NULL DEFAULT now(),
    criado_em     timestamptz                       NOT NULL DEFAULT now(),

    CONSTRAINT telefone_engajamento_pkey
        PRIMARY KEY (cnpj_basico, telefone, canal),

    CONSTRAINT telefone_engajamento_telefone_digits_check
        CHECK (telefone ~ '^[0-9]+$' AND length(telefone) >= 10),

    CONSTRAINT telefone_engajamento_fornecedor_fkey
        FOREIGN KEY (cnpj_basico)
        REFERENCES public.engajamento_fornecedores (cnpj_basico)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS telefone_engajamento_cnpj_canal_idx
    ON public.telefone_engajamento (cnpj_basico, canal);

CREATE INDEX IF NOT EXISTS telefone_engajamento_telefone_idx
    ON public.telefone_engajamento (telefone);
