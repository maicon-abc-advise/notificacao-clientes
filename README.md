# Sistema de e-mail / notificações

API em **FastAPI** para o fluxo de notificações (ABC Advise). Hoje o código cobre **envio de e-mail e SMS** (Zenvia), autenticação interna com API key, saúde da API e, opcionalmente, Docker/Redis.

**Requisitos:** Python 3.11 ou superior.

---

## 1. Estrutura de pastas (conforme o repositório)

A raiz do projeto (ex.: a pasta clonada como `notificacao-clientes/`) contém o seguinte. **Não existe** pasta com o nome `provedor`; a escolha do conector de mensageria fica no **módulo** `app.config.provedor_mensagens` (ficheiro `provedor_mensagens.py` dentro de `app/config/`, juntamente com `config.py`, `dependencias.py` e `security.py`).

### Raiz do repositório

```
.
├── app/                    # Pacote da aplicação
├── tests/                  # Testes (pytest)
├── alembic/                # Só com .gitkeep hoje; reservado a migrações
├── .env.example
├── .gitignore
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
└── README.md
```

### Dentro de `app/`

```
app/
├── __init__.py
├── main.py
├── api/                         # Borda HTTP
│   ├── __init__.py
│   ├── dto/                     # Corpos e respostas (Pydantic)
│   │   ├── __init__.py
│   │   └── modelos.py
│   ├── rotas/                   # Routers FastAPI
│   │   ├── __init__.py
│   │   ├── envio_mensagens.py
│   │   ├── ping_autenticado.py
│   │   └── saude.py
│   └── externo/                 # Conectores a serviços externos
│       ├── __init__.py
│       └── zenvia/
│           ├── __init__.py
│           ├── adaptador_envio.py
│           └── parametros.py
├── config/                      
│   ├── __init__.py
│   ├── config.py
│   ├── dependencias.py
│   ├── security.py
│   └── provedor_mensagens.py
├── excecoes/
│   ├── __init__.py
│   ├── erro.py
│   └── erro_provedor.py
├── repositorios/                 
│   └── __init__.py
└── servicos/
    ├── __init__.py
    └── mensageria/               # Portas, fábrica e composição e-mail/SMS
        ├── __init__.py
        ├── fabrica_provedor_mensagem.py
        ├── porta.py
        └── porta_composta.py
```

### O que é cada bloco (resumido)

| Local | Papel |
|--------|--------|
| `app.api.dto` + `app.api.rotas` | Contrato JSON e rotas (FastAPI). |
| `app.api.externo.zenvia` | Chamada HTTP à API v2 da Zenvia. |
| `app.config` | `Configuracao` a partir do `.env`, `Depends` compartilhado, leitura de `API_KEY` e ficheiro `provedor_mensagens` (qual conector de e-mail/SMS usar). |
| `app.excecoes` | `ErroEnvioZenvia`, `FalhaConfiguracaoProvedor` e similares. |
| `app.servicos.mensageria` | Abstração de “enviar mensagem” (porta + fábrica) sem lógica HTTP do Zenvia. |
| `app.repositorios` | Ainda reservada; podes preencher quando houver camada de persistência. |

A pasta **`analise-inicial/`** fica fora do Git (está no `.gitignore`) e não entra nessa árvore versionada.

---

## 2. Como rodar

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

### Opção B — Docker Compose (API + Redis)

```powershell
docker compose up --build
```

- API: **http://127.0.0.1:8000** / docs em **/docs**  
- Redis: **localhost:6379**  

Detalhe das variáveis: **`.env.example`**.

---

**Não comitar** `.env`, `.venv/`, `__pycache__/` (conforme **`.gitignore`**).
