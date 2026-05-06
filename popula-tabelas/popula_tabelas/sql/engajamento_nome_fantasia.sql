-- Nome vindo do payload de recebe-consulta (denormalizado no engajamento para dashboard / contexto).
ALTER TABLE public.engajamento_fornecedores
    ADD COLUMN IF NOT EXISTS nome_fantasia text;
