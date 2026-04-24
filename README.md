# Sistema de e-mail / notificações

API em **FastAPI** para o fluxo de notificações (ABC Advise). Hoje o repositório contém **infraestrutura mínima**: aplicação registrando routers em `rotas/`, rota de saúde e ambiente opcional com Docker.

**Requisitos:** Python 3.11 ou superior.

---

## 1. Estrutura de pastas (estado atual)

```
sistema-email/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI
│   ├── config/                 # Configurações 
│   │   └── __init__.py
│   ├── dominio/                # Regras / modelos de domínio 
│   │   └── __init__.py
│   ├── nucleo/                 # Nucleos e Configurações
│   │   └── __init__.py
│   ├── repositorios/           # Acesso a dados 
│   │   └── __init__.py
│   ├── servicos/               # Casos de uso / serviços 
│   │   └── __init__.py
│   └── rotas/                  # Endpoints HTTP 
│       └── __init__.py
├── alembic/                    
│   └── .gitkeep
├── tests/
│   └── teste_saude.py
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

Em `app/`, **`config/`**, **`dominio/`**, **`nucleo/`**, **`repositorios/`** e **`servicos/`** existem como **pacotes vazios** (só `__init__.py`) para você ir preenchendo; a única parte com rotas implementadas hoje é **`rotas/`**.

A pasta **`analise-inicial/`** fica só na sua máquina: está no **`.gitignore`** e não sobe para o GitHub.

---

## 2. Como rodar

### Opção A — ambiente virtual (desenvolvimento)

```powershell
cd caminho\para\sistema-email
py -3.12 -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"
copy .env.example .env
.\.venv\Scripts\uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- Documentação interativa: **http://127.0.0.1:8000/docs**
- Testes: `.\.venv\Scripts\python -m pytest`

### Opção B — Docker Compose (API + Redis)

```powershell
docker compose up --build
```

- API: **http://127.0.0.1:8000**
- Docs: **http://127.0.0.1:8000/docs**
- Redis: **localhost:6379**

Variáveis: veja `.env.example` (e opcionalmente um `.env` na raiz para o Compose).

---

**GitHub:** não commite `.env`, `.venv/`, `__pycache__/` nem a pasta `analise-inicial/` (ignorados no `.gitignore`).
