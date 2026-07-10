CREATE TABLE IF NOT EXISTS public.variaveis_sistema (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('int', 'float', 'bool', 'string', 'percent')),
    grupo TEXT NOT NULL,
    descricao TEXT NOT NULL DEFAULT '',
    editavel BOOLEAN NOT NULL DEFAULT true,
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_variaveis_sistema_grupo
    ON public.variaveis_sistema (grupo);
