# Sistema de e-mail / notificações

API em **FastAPI** para o fluxo de notificações (ABC Advise). Hoje o código cobre **envio de e-mail e SMS** (Zenvia), autenticação interna com API key, saúde da API, Docker/Redis e **templates** em **Postgres** (`public.templates_notificacao`). Os pedidos `POST /v1/mensagens/email` e `POST /v1/mensagens/sms` usam **só modo template**: `tipo_template` (enum alinhado à coluna `tipo`) + `contexto` (mapa para substituir `{{ chave }}`); o HTML e o texto SMS vêm da base. O **assunto** do e-mail é **inferido no servidor** a partir de `tipo_template` (`app/templates/assunto_email.py`), sem campo no JSON. Textos literais seguem o plano em `analise-inicial/PLANO_TEMPLATES.md` quando o mono-repo inclui essa pasta.

**Requisitos:** Python 3.11 ou superior.

---

## 1. Estrutura de pastas (conforme o repositório)

A raiz do projeto (ex.: a pasta clonada como `notificacao-clientes/`) contém o seguinte. **Não existe** pasta com o nome `provedor`; a escolha do conector de mensageria fica no **módulo** `app.config.provedor_mensagens` (ficheiro `provedor_mensagens.py` dentro de `app/config/`, juntamente com `config.py`, `dependencias.py` e `security.py`).

O código de negócio do envio está agrupado em **`app.mensageria`**. **`app.orquestracao`** e **`app.reenvio`** repetem a mesma subdivisão (`api`, `excecoes`, `repositorios`, `servicos`) para evolução futura; hoje estão só com pacotes vazios.

### Raiz do repositório

```
.
├── app/                    # Pacote da aplicação
├── tests/                  # Testes (pytest)
├── alembic/                # Só com .gitkeep hoje; reservado a migrações
├── .env.example
├── .gitignore
├── docker-compose.yml
├── docker-compose.postgres.yml  # só Postgres (templates), porta 5433
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
│   ├── repositorios/
│   │   └── __init__.py
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
    ├── api/__init__.py
    ├── excecoes/__init__.py
    ├── repositorios/__init__.py
    └── servicos/__init__.py
```

### O que é cada bloco (resumido)

| Local | Papel |
|--------|--------|
| `app.mensageria.api.dto` + `app.mensageria.api.rotas` | Contrato JSON e rotas (FastAPI). |
| `app.mensageria.api.externo.zenvia` | Chamada HTTP à API v2 da Zenvia. |
| `app.config` | `Configuracao` a partir do `.env`, `Depends` compartilhado, leitura de `API_KEY` e ficheiro `provedor_mensagens` (qual conector de e-mail/SMS usar). |
| `app.mensageria.excecoes` | `ErroEnvioZenvia`, `FalhaConfiguracaoProvedor` e similares. |
| `app.mensageria.servicos` | Abstração de “enviar mensagem” (porta + fábrica) sem lógica HTTP do Zenvia. |
| `app.mensageria.repositorios` | Reservada; preencher quando houver persistência neste domínio. |
| `app.templates` | Tabela `templates_notificacao` no Postgres, porta `PortaTemplates`, `RepositorioTemplatesPostgres`. |
| `app.orquestracao.*` / `app.reenvio.*` | Estrutura reservada (mesma convenção de pastas). |

A pasta **`analise-inicial/`** fica fora do Git (está no `.gitignore`) e não entra nessa árvore versionada.

---

## 2. Postgres só para templates (Docker)

Na **raiz deste projeto** (`notificacao-clientes/`, a pasta onde estão `app/`, `pyproject.toml` e este `README.md`), existe `docker-compose.postgres.yml` com um único serviço Postgres na porta **5433**, credenciais de desenvolvimento alinhadas ao `.env.example`.

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
