-- Corrige FK que aponta para fornecedores_teste: o UUID do fornecedor existe em usuario_fornecedor_teste.id.
-- Rode no mesmo schema onde estão emails_enviados / usuario_fornecedor (ex.: public).
-- Se o sufixo não for _teste, ajuste nomes de tabela, coluna e constraint.

ALTER TABLE public.emails_enviados
    DROP CONSTRAINT IF EXISTS emails_enviados_fornecedor_id_teste_fkey;

ALTER TABLE public.emails_enviados
    ADD CONSTRAINT emails_enviados_fornecedor_id_teste_fkey
    FOREIGN KEY (fornecedor_id_teste)
    REFERENCES public.usuario_fornecedor_teste (id)
    ON DELETE SET NULL;

-- Opcional: mesma correção para SMS (o nome da constraint pode variar; confira com \d sms_enviados)
-- ALTER TABLE public.sms_enviados DROP CONSTRAINT IF EXISTS sms_enviados_fornecedor_id_teste_fkey;
-- ALTER TABLE public.sms_enviados ADD CONSTRAINT sms_enviados_fornecedor_id_teste_fkey
--     FOREIGN KEY (fornecedor_id_teste) REFERENCES public.usuario_fornecedor_teste (id) ON DELETE SET NULL;
