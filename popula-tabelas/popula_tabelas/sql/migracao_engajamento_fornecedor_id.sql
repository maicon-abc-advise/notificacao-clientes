-- Migração legado: engajamento_usuarios + fornecedores.usuario_id → engajamento_fornecedores + fornecedor_id nas filas.
-- Idempotente. Pode rodar só com ``run_migracao_orquestracao.py`` (cria ``engajamento_fornecedores`` se faltar).

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

-- 1) Copiar engajamento por usuário para cada fornecedor vinculado; remover tabela antiga.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'engajamento_usuarios'
    ) THEN
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'fornecedores' AND column_name = 'usuario_id'
        ) THEN
            INSERT INTO public.engajamento_fornecedores (
                fornecedor_id,
                engajamento_email,
                engajamento_sms,
                engajamento_email_atualizado_em,
                engajamento_sms_atualizado_em,
                engajamento_atualizado_em,
                ultimo_lembrete_limite_semanal_em,
                recebe_email,
                aparicoes_mes,
                aparicoes_mes_referencia
            )
            SELECT
                f.fornecedor_id,
                e.engajamento_email,
                e.engajamento_sms,
                e.engajamento_email_atualizado_em,
                e.engajamento_sms_atualizado_em,
                e.engajamento_atualizado_em,
                e.ultimo_lembrete_limite_semanal_em,
                e.recebe_email,
                e.aparicoes_mes,
                e.aparicoes_mes_referencia
            FROM public.fornecedores f
            INNER JOIN public.engajamento_usuarios e ON f.usuario_id = e.usuario_id
            ON CONFLICT (fornecedor_id) DO NOTHING;
        END IF;

        DROP TABLE public.engajamento_usuarios;
    END IF;
END $$;

-- 2) emails_enviados: usuario_id → fornecedor_id
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'emails_enviados' AND column_name = 'usuario_id'
    ) THEN
        ALTER TABLE public.emails_enviados ADD COLUMN IF NOT EXISTS fornecedor_id uuid;

        UPDATE public.emails_enviados AS e
        SET fornecedor_id = m.fornecedor_id
        FROM (
            SELECT DISTINCT ON (f.usuario_id) f.usuario_id AS u, f.fornecedor_id
            FROM public.fornecedores f
            WHERE f.usuario_id IS NOT NULL
            ORDER BY f.usuario_id, f.fornecedor_id
        ) AS m
        WHERE e.usuario_id IS NOT NULL AND e.usuario_id = m.u;

        DROP INDEX IF EXISTS idx_emails_enviados_usuario;
        ALTER TABLE public.emails_enviados DROP COLUMN usuario_id;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_emails_enviados_fornecedor
    ON public.emails_enviados (fornecedor_id)
    WHERE fornecedor_id IS NOT NULL;

-- 3) sms_enviados
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'sms_enviados' AND column_name = 'usuario_id'
    ) THEN
        ALTER TABLE public.sms_enviados ADD COLUMN IF NOT EXISTS fornecedor_id uuid;

        UPDATE public.sms_enviados AS s
        SET fornecedor_id = m.fornecedor_id
        FROM (
            SELECT DISTINCT ON (f.usuario_id) f.usuario_id AS u, f.fornecedor_id
            FROM public.fornecedores f
            WHERE f.usuario_id IS NOT NULL
            ORDER BY f.usuario_id, f.fornecedor_id
        ) AS m
        WHERE s.usuario_id IS NOT NULL AND s.usuario_id = m.u;

        DROP INDEX IF EXISTS idx_sms_enviados_usuario;
        ALTER TABLE public.sms_enviados DROP COLUMN usuario_id;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_sms_enviados_fornecedor
    ON public.sms_enviados (fornecedor_id)
    WHERE fornecedor_id IS NOT NULL;

-- 4) fornecedores.usuario_id
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'fornecedores' AND column_name = 'usuario_id'
    ) THEN
        DROP INDEX IF EXISTS idx_fornecedores_usuario_id;
        ALTER TABLE public.fornecedores DROP COLUMN usuario_id;
    END IF;
END $$;
