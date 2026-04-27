CREATE TABLE IF NOT EXISTS public.templates_notificacao (
    id TEXT PRIMARY KEY,
    tipo TEXT NOT NULL UNIQUE,
    email TEXT NULL,
    sms TEXT NOT NULL
);
