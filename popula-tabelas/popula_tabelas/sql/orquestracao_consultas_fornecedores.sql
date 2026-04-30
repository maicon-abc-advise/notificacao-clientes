-- Consultas e fornecedores (orquestração). Aplicar com: python popula-tabelas/run.py (ou popula_tabelas)

CREATE TABLE IF NOT EXISTS public.consultas (
    id uuid PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    status text NOT NULL DEFAULT 'registrada',
    parametros jsonb NOT NULL DEFAULT '{}'::jsonb,
    resultados jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS public.fornecedores (
    fornecedor_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cnpj text NOT NULL,
    nome text,
    email text,
    telefone text,
    ativo boolean NOT NULL DEFAULT true,
    aparicoes_busca int NOT NULL DEFAULT 0,
    creditos int NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fornecedores_cnpj_chk CHECK (cnpj ~ '^[0-9]{14}$'),
    CONSTRAINT fornecedores_cnpj_uniq UNIQUE (cnpj)
);

CREATE TABLE IF NOT EXISTS public.engajamento_fornecedores (
    fornecedor_id uuid PRIMARY KEY REFERENCES public.fornecedores(fornecedor_id) ON DELETE CASCADE,
    engajamento_email text NOT NULL DEFAULT 'ativo',
    engajamento_sms text NOT NULL DEFAULT 'ativo',
    engajamento_email_atualizado_em timestamptz,
    engajamento_sms_atualizado_em timestamptz,
    engajamento_atualizado_em timestamptz NOT NULL DEFAULT now(),
    ultimo_lembrete_limite_semanal_em timestamptz,
    recebe_email boolean NOT NULL DEFAULT true,
    aparicoes_mes int NOT NULL DEFAULT 0,
    aparicoes_mes_referencia varchar(7) NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_consultas_created_at ON public.consultas (created_at DESC);
