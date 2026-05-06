-- Engajamento: listas JSON por contato + agregados (ativo / em_analise / inativo).
-- Requer coluna ``cnpj_basico`` e UNIQUE em ``engajamento_fornecedores`` (como no código da orquestração).

ALTER TABLE public.engajamento_fornecedores
    ADD COLUMN IF NOT EXISTS contatos_email jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS contatos_sms jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS ultimo_envio_email_endereco text,
    ADD COLUMN IF NOT EXISTS ultimo_envio_sms_endereco text;

ALTER TABLE public.engajamento_fornecedores
    DROP COLUMN IF EXISTS recebe_email;

-- Normaliza valores antigos granulares nos agregados (ambiente sem migração fina).
UPDATE public.engajamento_fornecedores
SET engajamento_email = 'ativo'
WHERE engajamento_email IS NOT NULL
  AND engajamento_email NOT IN ('ativo', 'em_analise', 'inativo');

UPDATE public.engajamento_fornecedores
SET engajamento_sms = 'ativo'
WHERE engajamento_sms IS NOT NULL
  AND engajamento_sms NOT IN ('ativo', 'em_analise', 'inativo');
