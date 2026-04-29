-- Migração única: ``engajamento_estado`` → ``engajamento_email`` + ``engajamento_sms`` (+ timestamps por canal).
-- Bases novas: use apenas ``reenvio.sql`` atualizado (já com as colunas novas).

BEGIN;

ALTER TABLE public.engajamento_usuarios
    ADD COLUMN IF NOT EXISTS engajamento_email text,
    ADD COLUMN IF NOT EXISTS engajamento_sms text,
    ADD COLUMN IF NOT EXISTS engajamento_email_atualizado_em timestamptz,
    ADD COLUMN IF NOT EXISTS engajamento_sms_atualizado_em timestamptz;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'engajamento_usuarios'
          AND column_name = 'engajamento_estado'
    ) THEN
        UPDATE public.engajamento_usuarios
        SET
            engajamento_email = CASE
                WHEN engajamento_estado = 'ativo' THEN 'ativo'
                WHEN engajamento_estado LIKE 'email_%' THEN engajamento_estado
                ELSE 'ativo'
            END,
            engajamento_sms = CASE
                WHEN engajamento_estado = 'ativo' THEN 'ativo'
                WHEN engajamento_estado LIKE 'sms_%' THEN engajamento_estado
                ELSE 'ativo'
            END;
        ALTER TABLE public.engajamento_usuarios DROP COLUMN engajamento_estado;
    END IF;
END $$;

UPDATE public.engajamento_usuarios SET engajamento_email = 'ativo' WHERE engajamento_email IS NULL;
UPDATE public.engajamento_usuarios SET engajamento_sms = 'ativo' WHERE engajamento_sms IS NULL;

ALTER TABLE public.engajamento_usuarios
    ALTER COLUMN engajamento_email SET DEFAULT 'ativo',
    ALTER COLUMN engajamento_sms SET DEFAULT 'ativo',
    ALTER COLUMN engajamento_email SET NOT NULL,
    ALTER COLUMN engajamento_sms SET NOT NULL;

COMMIT;
