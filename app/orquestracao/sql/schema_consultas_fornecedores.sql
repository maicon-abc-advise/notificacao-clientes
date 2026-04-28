-- Consultas e fornecedores (orquestração). Aplicar com: python -m app.orquestracao.aplicar_schema

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
    usuario_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fornecedores_cnpj_chk CHECK (cnpj ~ '^[0-9]{14}$'),
    CONSTRAINT fornecedores_cnpj_uniq UNIQUE (cnpj)
);

CREATE INDEX IF NOT EXISTS idx_consultas_created_at ON public.consultas (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_fornecedores_usuario_id ON public.fornecedores (usuario_id)
    WHERE usuario_id IS NOT NULL;
