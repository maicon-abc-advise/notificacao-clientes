-- Colunas agregadas de WhatsApp e ligação em ``engajamento_fornecedores``.

ALTER TABLE public.engajamento_fornecedores
    ADD COLUMN IF NOT EXISTS engajamento_whatsapp text NOT NULL DEFAULT 'ativo';

ALTER TABLE public.engajamento_fornecedores
    ADD COLUMN IF NOT EXISTS engajamento_whatsapp_atualizado_em timestamptz;

ALTER TABLE public.engajamento_fornecedores
    ADD COLUMN IF NOT EXISTS ultimo_envio_whatsapp_telefone text;

ALTER TABLE public.engajamento_fornecedores
    ADD COLUMN IF NOT EXISTS engajamento_ligacao text NOT NULL DEFAULT 'ativo';

ALTER TABLE public.engajamento_fornecedores
    ADD COLUMN IF NOT EXISTS engajamento_ligacao_atualizado_em timestamptz;

ALTER TABLE public.engajamento_fornecedores
    ADD COLUMN IF NOT EXISTS ultimo_envio_ligacao_telefone text;
