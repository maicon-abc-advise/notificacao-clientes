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
├── popula-tabelas/         # DDL + seed de dev/teste (um comando; ver secção 2)
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
│   ├── modelo.py         # TemplateNotificacao, CodigoTipoTemplate
│   ├── porta.py          # PortaTemplates (Protocol)
│   └── repositorio_postgres.py
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
    ├── redis_app.py
    ├── api/
    │   ├── dependencias_webhook.py
    │   ├── dto/webhook_zenvia.py
    │   └── rotas/          # webhooks, interno, teste-pipeline
    ├── excecoes/
    ├── repositorios/       # Redis (filas) + Postgres (idempotência de webhooks)
    └── servicos/
```

### O que é cada bloco (resumido)

| Local | Papel |
|--------|--------|
| `app.mensageria.api.dto` + `app.mensageria.api.rotas` | Contrato JSON e rotas (FastAPI). |
| `app.mensageria.api.externo.zenvia` | Chamada HTTP à API v2 da Zenvia. |
| `app.config` | `Configuracao` a partir do `.env` (pares `*_TEST`/`*_PROD` + `AMBIENTE`), `Depends` compartilhado e provedores de e-mail/SMS. |
| `app.mensageria.excecoes` | `ErroEnvioZenvia`, `FalhaConfiguracaoProvedor` e similares. |
| `app.mensageria.servicos` | Abstração de “enviar mensagem” (porta + fábrica) sem lógica HTTP do Zenvia. |
| `app.mensageria.repositorios` | `emails_enviados` e `sms_enviados` (Postgres) após envio pela API. |
| `app.templates` | Tabela `templates_notificacao` no Postgres, porta `PortaTemplates`, `RepositorioTemplatesPostgres`. |
| `app.reenvio` | Webhooks, Redis (`emails-esperando-confirmacao`, `sms-pendente`), rotas internas (sweep, listagem SMS). |
| `app.orquestracao.*` | Reservado. |

A pasta **`analise-inicial/`** pode conter notas de análise (não faz parte do arranque da API).

---

## 2. Postgres + Redis (Docker local)

Na **raiz deste projeto** existe `docker-compose.postgres.yml` com:

- **Postgres** na porta **5433** (templates + tabelas de reenvio: use `DATABASE_URL_TEST` / `DATABASE_URL` no `.env` conforme **`.env.example`**);
- **Redis** na porta **6379** (e-mails esperando confirmação + fila `sms-pendente`).

Chaves Redis usadas pelo reenvio: **`emails-esperando-confirmacao:*`** (pós-envio de e-mail, webhooks e sweep) e **`sms-pendente:*`** (fila de SMS antes do disparo). Dados antigos em `email:pendente:*` / `sms:pendente:*` **não** são migrados automaticamente.

Credenciais alinhadas ao **`.env.example`** (`REDIS_URL_TEST` / `REDIS_URL_PROD`, mocks globais, Zenvia só `*_PROD` ou sem sufixo).

**Subir só o banco:**

```powershell
cd caminho\para\notificacao-clientes
docker compose -f docker-compose.postgres.yml up -d
```

**Parar:**

```powershell
docker compose -f docker-compose.postgres.yml down
```

**Popular tabelas (só desenvolvimento / teste)** — não faz parte do pacote publicado da API; em produção o schema vem de migrações ou do pipeline de implantação. Na raiz do repositório, com Postgres acessível e variáveis de base no `.env` (a app resolve `DATABASE_URL_*` conforme `AMBIENTE`):

```powershell
cd caminho\para\notificacao-clientes
.\.venv\Scripts\python popula-tabelas\run.py
```

Isso aplica em sequência DDL + seed de templates, DDL de reenvio e DDL de orquestração. SQL e dados em `popula-tabelas/popula_tabelas/`. Para conferir templates: `SELECT id, tipo, email IS NULL AS sem_email, length(sms) FROM public.templates_notificacao;`.

**Bases que já tinham `engajamento_usuarios.engajamento_estado` (coluna única):** aplique uma vez o script `popula-tabelas/popula_tabelas/sql/migrate_engajamento_dois_canais.sql` no Postgres antes de subir esta versão da API (ele cria `engajamento_email` / `engajamento_sms`, copia dados e remove a coluna antiga). Instalações novas só com `reenvio.sql` atual já nascem com as duas colunas.

Para aplicar só um bloco (ex.: só templates), use as funções em `popula_tabelas.aplicar` a partir desse diretório (mesmo `PYTHONPATH` que `run.py`).

---

## 2.1. Testes locais sem Zenvia (`/v1/interno/teste-pipeline/`)

Rotas para **simular** envio de e-mail/SMS e webhooks **sem** chamar a API da Zenvia (útil para exercitar Redis + Postgres em desenvolvimento).

**Ativar:** com **`AMBIENTE=local`** as rotas ficam disponíveis (não há variável `TESTE_PIPELINE_HABILITADO`). Com **`AMBIENTE=producao`** não são expostas.

**Autenticação:** igual às outras rotas internas — **`Authorization: Bearer <API_KEY>`** ou **`X-Api-Key`**.

**Mocks:** `USE_ZENVIA_MOCK` e `USE_BIGDATACORP_MOCK` são únicos (não há pares por ambiente). Credenciais Zenvia reais: `ZENVIA_*_PROD` ou fallback sem sufixo; Big Data Corp: `BIGDATACORP_API_BASE_URL` e `BIGDATACORP_ACCESS_TOKEN` quando o mock estiver desligado (ver **`.env.example`**).

| Método | Caminho (prefixo `/v1/interno/teste-pipeline`) | Resumo |
|--------|--------------------------------------------------|--------|
| `POST` | `/engajamento` | Garante uma linha em `engajamento_usuarios` (UUID opcional no body). |
| `POST` | `/simular-email-enviado` | Pós-envio simulado: Redis `emails-esperando-confirmacao:*` + `emails_enviados` (+ engajamento opcional), com `messageId` falso. |
| `POST` | `/disparar-webhook-email` | Monta um `MESSAGE_STATUS` e usa a mesma lógica que `POST /v1/webhooks/notificacao/email`. |
| `POST` | `/simular-sms-enviado` | Remove `sms-pendente:*` se existir e grava `sms_enviados` com id Zenvia falso. |
| `POST` | `/cenario-email-bounce-gera-sms-redis` | E-mail falso + webhook de bounce “duro” → entrada na fila `sms-pendente` (Redis). |

No **Swagger** (`/docs`, grupo **teste-pipeline**) vês os corpos e testas no browser.

**Webhooks de status** (fora deste modo; o corpo segue o contrato do provedor): `POST /v1/webhooks/notificacao/email` e `POST /v1/webhooks/notificacao/sms`. Com **`ZENVIA_WEBHOOK_SECRET`** definido, inclui **`X-Webhook-Secret`** no pedido. Esquema do corpo: modelo **WebhookMessageStatusZenvia** no OpenAPI.

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
