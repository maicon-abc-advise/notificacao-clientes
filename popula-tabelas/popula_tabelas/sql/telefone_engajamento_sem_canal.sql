-- Permite linha placeholder ``sem_canal`` / ``sem_status`` para telefones descobertos.

ALTER TABLE public.telefone_engajamento
    DROP CONSTRAINT IF EXISTS telefone_engajamento_canal_check;

ALTER TABLE public.telefone_engajamento
    ADD CONSTRAINT telefone_engajamento_canal_check
        CHECK (canal IN ('sem_canal', 'sms', 'whatsapp', 'ligacao'));
