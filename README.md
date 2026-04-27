# Sistema de e-mail / notificações

API em **FastAPI** para o fluxo de notificações (ABC Advise). Hoje o código cobre **envio de e-mail e SMS** (Zenvia), autenticação interna com API key, saúde da API, Docker/Redis e **templates** em **Postgres** (`public.templates_notificacao`). Os pedidos `POST /v1/mensagens/email` e `POST /v1/mensagens/sms` usam **só modo template**: `tipo_template` (enum alinhado à coluna `tipo`) + `contexto` (mapa para substituir `{{ chave }}`); o HTML e o texto SMS vêm da base. O **assunto** do e-mail é **inferido no servidor** a partir de `tipo_template` (`app/templates/assunto_email.py`), sem campo no JSON.

**Requisitos:** Python 3.11 ou superior.

---

## 1. Estrutura de pastas (conforme o repositório)

A raiz do projeto (ex.: a pasta clonada como `notificacao-clientes/`) contém o seguinte. **Não existe** pasta com o nome `provedor`; a escolha do conector de mensageria fica no **módulo** `app.config.provedor_mensagens` (ficheiro `provedor_mensagens.py` dentro de `app/config/`, juntamente com `config.py`, `dependencias.py` e `security.py`).

O código de negócio do envio está agrupado em **`app.mensageria`**. **`app.reenvio`** implementa filas e webhooks; **`app.orquestracao`** permanece reservado.

### Raiz do repositório

```
.
├── app/                    # Pacote da aplicação
├── tests/                  # Testes (pytest)
├── alembic/                # Só com .gitkeep hoje; reservado a migrações
├── .env.example
├── .gitignore
├── docker-compose.yml
├── docker-compose.postgres.yml  # Postgres (5433) + Redis (6379) para dev local
├── Dockerfile
├── pyproject.toml
└── README.md
```

### Dentro de `app/`

```
app/
├── __init__.py
├── main.py
├── config/
│   ├── __init__.py
│   ├── config.py
│   ├── dependencias.py
│   ├── security.py
│   └── provedor_mensagens.py
├── templates/
│   ├── __init__.py
│   ├── banco.py          # aplicar schema.sql + seed (asyncpg)
│   ├── dados_seed.py     # HTML/SMS literais
│   ├── modelo.py         # TemplateNotificacao, CodigoTipoTemplate
│   ├── popular.py        # python -m app.templates.popular
│   ├── porta.py          # PortaTemplates (Protocol)
│   ├── repositorio_postgres.py
│   └── sql/
│       └── schema.sql    # CREATE TABLE (sem Alembic)
├── mensageria/
│   ├── __init__.py
│   ├── repositorios/
│   │   ├── __init__.py
│   │   ├── postgres_emails_enviados.py
│   │   └── postgres_sms_enviados.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── dto/
│   │   │   ├── __init__.py
│   │   │   └── modelos.py
│   │   ├── rotas/
│   │   │   ├── __init__.py
│   │   │   ├── envio_mensagens.py
│   │   │   ├── ping_autenticado.py
│   │   │   └── saude.py
│   │   └── externo/
│   │       ├── __init__.py
│   │       └── zenvia/
│   │           ├── __init__.py
│   │           ├── adaptador_envio.py
│   │           └── parametros.py
│   ├── excecoes/
│   │   ├── __init__.py
│   │   ├── erro.py
│   │   └── erro_provedor.py
│   └── servicos/
│       ├── __init__.py
│       ├── fabrica_provedor_mensagem.py
│       ├── porta.py
│       └── porta_composta.py
├── orquestracao/
│   ├── __init__.py
│   ├── api/__init__.py
│   ├── excecoes/__init__.py
│   ├── repositorios/__init__.py
│   └── servicos/__init__.py
└── reenvio/
    ├── __init__.py
    ├── aplicar_schema.py   # python -m app.reenvio.aplicar_schema
    ├── redis_app.py
    ├── api/
    │   ├── dependencias_webhook.py
    │   ├── dto/webhook_zenvia.py
    │   └── rotas/          # webhooks, interno, teste-pipeline
    ├── excecoes/
    ├── repositorios/       # Redis (filas) + Postgres (idempotência de webhooks)
    ├── servicos/
    └── sql/schema.sql      # emails_enviados, sms_enviados, engajamento_usuarios, webhook_eventos_processados
```

### O que é cada bloco (resumido)

| Local | Papel |
|--------|--------|
| `app.mensageria.api.dto` + `app.mensageria.api.rotas` | Contrato JSON e rotas (FastAPI). |
| `app.mensageria.api.externo.zenvia` | Chamada HTTP à API v2 da Zenvia. |
| `app.config` | `Configuracao` a partir do `.env`, `Depends` compartilhado, leitura de `API_KEY` e ficheiro `provedor_mensagens` (qual conector de e-mail/SMS usar). |
| `app.mensageria.excecoes` | `ErroEnvioZenvia`, `FalhaConfiguracaoProvedor` e similares. |
| `app.mensageria.servicos` | Abstração de “enviar mensagem” (porta + fábrica) sem lógica HTTP do Zenvia. |
| `app.mensageria.repositorios` | `emails_enviados` e `sms_enviados` (Postgres) após envio pela API. |
| `app.templates` | Tabela `templates_notificacao` no Postgres, porta `PortaTemplates`, `RepositorioTemplatesPostgres`. |
| `app.reenvio` | Webhooks, filas Redis, rotas internas (sweep, SMS pendentes), `app.reenvio.aplicar_schema`. |
| `app.orquestracao.*` | Reservado. |

A pasta **`analise-inicial/`** pode conter notas de análise (não faz parte do arranque da API).

---

## 2. Postgres + Redis (Docker local)

Na **raiz deste projeto** existe `docker-compose.postgres.yml` com:

- **Postgres** na porta **5433** (templates + tabelas de reenvio no mesmo `DATABASE_URL`);
- **Redis** na porta **6379** (filas de e-mail e SMS pendentes).

Credenciais alinhadas ao **`.env.example`** (`REDIS_URL=redis://localhost:6379/0`).

**Subir só o banco:**

```powershell
cd caminho\para\notificacao-clientes
docker compose -f docker-compose.postgres.yml up -d
```

**Parar:**

```powershell
docker compose -f docker-compose.postgres.yml down
```

**Popular tabela e dados** (com o Postgres acessível e `DATABASE_URL` no ambiente ou no `.env`):

```powershell
cd caminho\para\notificacao-clientes
.\.venv\Scripts\python -m app.templates.popular
```

O comando aplica `app/templates/sql/schema.sql` e insere/atualiza as quatro linhas (`ON CONFLICT (tipo) DO UPDATE`). Para conferir: `SELECT id, tipo, email IS NULL AS sem_email, length(sms) FROM public.templates_notificacao;`.

**Tabelas de reenvio** (entre outras: `emails_enviados`, `sms_enviados`, `engajamento_usuarios`, `webhook_eventos_processados`):

```powershell
.\.venv\Scripts\python -m app.reenvio.aplicar_schema
```

---

## 2.1. Testes locais sem Zenvia (`/v1/interno/teste-pipeline/`)

Rotas para **simular** envio de e-mail/SMS e webhooks **sem** chamar a API da Zenvia (útil para exercitar Redis + Postgres em desenvolvimento).

**Ativar no `.env`:**

```env
TESTE_PIPELINE_HABILITADO=true
```

(Em produção pública mantém **`false`** ou omite.)

**Autenticação:** igual às outras rotas internas — **`Authorization: Bearer <API_KEY>`** ou **`X-Api-Key`** (valor de **`API_KEY`** no `.env`).

| Método | Caminho (prefixo `/v1/interno/teste-pipeline`) | Resumo |
|--------|--------------------------------------------------|--------|
| `POST` | `/engajamento` | Garante uma linha em `engajamento_usuarios` (UUID opcional no body). |
| `POST` | `/simular-email-enviado` | Pós-envio simulado: Redis `email:pendente:*` + `emails_enviados` (+ engajamento opcional), com `messageId` falso. |
| `POST` | `/disparar-webhook-email` | Monta um `MESSAGE_STATUS` e usa a mesma lógica que `POST /v1/webhooks/zenvia/email`. |
| `POST` | `/simular-sms-enviado` | Remove `sms:pendente:*` se existir e grava `sms_enviados` com id Zenvia falso. |
| `POST` | `/cenario-email-bounce-gera-sms-redis` | E-mail falso + webhook de bounce “duro” → SMS pendente no Redis. |

No **Swagger** (`/docs`, grupo **teste-pipeline**) vês os corpos e testas no browser.

**Webhooks reais Zenvia** (fora deste modo): `POST /v1/webhooks/zenvia/email` e `POST /v1/webhooks/zenvia/sms`. Com **`ZENVIA_WEBHOOK_SECRET`** definido, inclui **`X-Webhook-Secret`** no pedido. Esquema do corpo: modelo **WebhookMessageStatusZenvia** no OpenAPI.

**Documentação complementar** (fluxos em diagrama): `../analise-inicial/README-REENVIO.md` se o clone incluir a pasta `analise-inicial/`.

---

## 3. Como rodar

### Opção A — ambiente virtual (desenvolvimento)

```powershell
cd caminho\para\esta-pasta
py -3.12 -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"
copy .env.example .env
.\.venv\Scripts\uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- Documentação: **http://127.0.0.1:8000/docs**  
- Testes: `.\.venv\Scripts\python -m pytest`

### Opção B — Docker Compose (API + Redis, sem Postgres)

```powershell
docker compose up --build
```

- API: **http://127.0.0.1:8000** / docs em **/docs**  
- Redis: **localhost:6379**  

Detalhe das variáveis: **`.env.example`**.

---

**Não comitar** `.env`, `.venv/`, `__pycache__/` (conforme **`.gitignore`**).
