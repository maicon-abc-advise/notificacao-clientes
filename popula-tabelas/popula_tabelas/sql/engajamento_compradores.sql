CREATE TABLE IF NOT EXISTS public.engajamento_compradores (
    telefone text PRIMARY KEY,
    comprador_id uuid,
    primeira_consulta_sem_cadastro boolean NOT NULL DEFAULT false,
    converteu boolean NOT NULL DEFAULT false,
    criado_em timestamptz NOT NULL DEFAULT now(),
    atualizado_em timestamptz NOT NULL DEFAULT now(),
    converteu_em timestamptz
);
