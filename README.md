# Sistema de e-mail / notificações

API em **FastAPI** para o fluxo de notificações (ABC Advise). 
**Requisitos:** Python 3.11 ou superior.

---

## 1. Estrutura de pastas 

O código de negócio do envio está agrupado em **`app.mensageria`**. **`app.reenvio`** implementa filas e webhooks para receber feedbacks e reenvios; **`app.orquestracao`** é responsável por transformar uma consulta em um envio de mensagem.

### Raiz do repositório

```
.
├── app/                    
├── popula-tabelas/         
├── tests/                  
├── alembic/                
├── .env.example
├── .gitignore
├── docker-compose.yml
├── docker-compose.postgres.yml  
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
│   ├── modelo.py
│   ├── porta.py
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
│   ├── api/
│   │   ├── __init__.py
│   │   ├── dependencias.py
│   │   ├── router.py
│   │   ├── dto/
│   │   │   ├── __init__.py
│   │   │   ├── recebe_consulta_dto.py
│   │   │   └── verificar_creditos_dto.py
│   │   └── rotas/
│   │       ├── __init__.py
│   │       ├── emails_pendentes_rota.py
│   │       ├── recebe_consulta_rota.py
│   │       └── verificar_creditos_rota.py
│   ├── externo/
│   │   └── bigdatacorp/
│   │       ├── __init__.py
│   │       ├── adaptador_api.py
│   │       └── adaptador_mock.py
│   ├── excecoes/
│   │   └── __init__.py
│   ├── repositorios/
│   │   ├── __init__.py
│   │   ├── consultas_repo.py
│   │   ├── engajamento_consulta_repo.py
│   │   ├── fornecedores_repo.py
│   │   └── redis_emails_pendentes_repo.py
│   └── servicos/
│       ├── __init__.py
│       ├── receber_consulta_servico.py
│       ├── verificar_creditos_servico.py
│       └── auxiliares/
│           ├── __init__.py
│           ├── decidir_canal_e_cadencia.py
│           ├── enfileirar_ou_enviar_interno.py
│           ├── enriquecer_contato_fornecedor.py
│           ├── montar_pedido_mensagem.py
│           ├── porta_enriquecimento_contato.py
│           └── ultimo_envio_qualquer_canal.py
└── reenvio/
    ├── __init__.py
    ├── redis_app.py
    ├── api/
    │   ├── dependencias_webhook.py
    │   ├── dto/webhook_zenvia.py
    │   └── rotas/
    ├── excecoes/
    ├── repositorios/
    └── servicos/
```

---

## 2. Ambiente local vs produção e mocks

A variável **`AMBIENTE`** (`local`, `dev`, `development` → tratado como local; `producao`, `prod`, `production`, `produção` → produção) define **qual par de URLs** a aplicação usa para Redis e Postgres, não se os provedores externos são mockados.

- **Local:** entram `REDIS_URL_TEST` e `DATABASE_URL_TEST`. Se algum estiver vazio, vale o fallback `REDIS_URL` e `DATABASE_URL` (este último tem default no código apontando para Postgres em `127.0.0.1:5433`).
- **Produção:** entram `REDIS_URL_PROD` e `DATABASE_URL_PROD`, com o mesmo tipo de fallback (`REDIS_URL`, `DATABASE_URL`) quando faltar o par `*_PROD`.

**Mocks (independentes do `AMBIENTE`):**

- **`USE_ZENVIA_MOCK`:** `true` → envio de e-mail/SMS pela Zenvia é simulado (sem HTTP). `false` → usa a API real; credenciais em `ZENVIA_*_PROD` ou, sem sufixo, o fallback esperado pelo código (ex.: `ZENVIA_API_TOKEN`).
- **`USE_BIGDATACORP_MOCK`:** `true` → dados da Big Data Corp vêm do adaptador mock. `false` → espera `BIGDATACORP_API_BASE_URL` e `BIGDATACORP_ACCESS_TOKEN` para chamadas reais (conforme **`.env.example`**).

Ou seja: você pode rodar **`AMBIENTE=local`** com mocks ligados e apontar Redis/Postgres do Docker na sua máquina, ou **`AMBIENTE=producao`** em deploy com `*_PROD` e mocks desligados para integrações reais — os dois eixos (URLs de infra vs flags de mock) se combinam, mas não são a mesma coisa.

---

## 3. Postgres + Redis (Docker local)

Na **raiz deste projeto** existe `docker-compose.postgres.yml` com:

- **Postgres** na porta **5433** (templates + tabelas de reenvio: use `DATABASE_URL_TEST` / `DATABASE_URL` no `.env` conforme **`.env.example`**);
- **Redis** na porta **6379** (e-mails esperando confirmação + fila `sms-pendente`).

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

**Popular tabelas (só desenvolvimento / teste)**:

```powershell
cd caminho\para\notificacao-clientes
.\.venv\Scripts\python popula-tabelas\run.py
```

**Acessar o Redis dentro do contêiner** (CLI interativo; sair com `quit`):

```powershell
docker compose -f docker-compose.postgres.yml exec redis-local redis-cli
```

**Acessar o Postgres dentro do contêiner** e listar tabelas:

```powershell
docker compose -f docker-compose.postgres.yml exec postgres-templates psql -U notificacao -d notificacao
```

No `psql`, para listar tabelas do schema público: `\dt`

---

## 4. Como rodar

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

### Dashboard (`notificacao-clientes-dashboard`)

- Rotas internas só de leitura: prefixo **`/v1/interno/dashboard`** (header **`X-Api-Key`** igual às outras rotas internas). Instruções de execução: README na pasta do dashboard.
- Ao correr **`python popula-tabelas/run.py`**, após o `reenvio.sql` é aplicada uma migração que remove a coluna legada **`zenvia_ultimo_code`** (se existir) e recria o `CHECK` de **`status_ultimo`** em **`emails_enviados`** e **`sms_enviados`** para permitir também o valor **`lido`** (além de `processando`, `enviado`, `falha_definitiva`, `reprocessar`). No **Supabase**, se não correres o `run.py`, executa o equivalente: `DROP COLUMN IF EXISTS zenvia_ultimo_code` e atualiza o constraint conforme o DDL em `popula-tabelas/popula_tabelas/aplicar.py` (`_migrar_status_ultimo_lido_e_limpar_zenvia`).

---

**Não comitar** `.env`, `.venv/`, `__pycache__/` (conforme **`.gitignore`**).
