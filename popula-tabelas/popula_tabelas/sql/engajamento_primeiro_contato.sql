-- Marca se o CNPJ apareceu primeiro via recebe_consulta antes de existir em usuario_fornecedor.
-- NULL = legado / regra ainda não observada; false = primeiro contato sem cadastro prévio.
ALTER TABLE public.engajamento_fornecedores
    ADD COLUMN IF NOT EXISTS cadastrado_primeiro_contato boolean;
