-- Créditos por fornecedor (bancos criados antes da coluna). Idempotente.
ALTER TABLE public.fornecedores
    ADD COLUMN IF NOT EXISTS creditos int NOT NULL DEFAULT 0;
