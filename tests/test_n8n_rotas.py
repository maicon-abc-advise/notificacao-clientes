from __future__ import annotations

import asyncio
import time

from fastapi.testclient import TestClient

from app.main import app
from app.orquestracao.repositorios.redis_emails_pendentes_repo import RepositorioEmailsPendenteRedis
import app.reenvio.api.rotas.interno_n8n as interno_n8n
from app.reenvio.repositorios.redis_sms_pendente import RepositorioSmsPendenteRedis


class _FakeRedisPipeline:
    def __init__(self, redis: "_FakeRedis") -> None:
        self._redis = redis
        self._ops: list[tuple[str, tuple, dict]] = []

    def hset(self, *args, **kwargs) -> "_FakeRedisPipeline":
        self._ops.append(("hset", args, kwargs))
        return self

    def zadd(self, *args, **kwargs) -> "_FakeRedisPipeline":
        self._ops.append(("zadd", args, kwargs))
        return self

    def delete(self, *args, **kwargs) -> "_FakeRedisPipeline":
        self._ops.append(("delete", args, kwargs))
        return self

    def zrem(self, *args, **kwargs) -> "_FakeRedisPipeline":
        self._ops.append(("zrem", args, kwargs))
        return self

    async def execute(self) -> list[object]:
        saida: list[object] = []
        for nome, args, kwargs in self._ops:
            metodo = getattr(self._redis, nome)
            saida.append(await metodo(*args, **kwargs))
        self._ops.clear()
        return saida


class _FakeRedis:
    def __init__(self) -> None:
        self._strings: dict[str, str] = {}
        self._hashes: dict[str, dict[str, str]] = {}
        self._zsets: dict[str, dict[str, float]] = {}
        self._expiracoes: dict[str, float] = {}

    def pipeline(self, transaction: bool = True) -> _FakeRedisPipeline:
        _ = transaction
        return _FakeRedisPipeline(self)

    async def aclose(self) -> None:
        return None

    def _expirado(self, key: str) -> bool:
        exp = self._expiracoes.get(key)
        return exp is not None and exp <= time.time()

    def _purge(self, key: str) -> None:
        if not self._expirado(key):
            return
        self._strings.pop(key, None)
        self._hashes.pop(key, None)
        self._zsets.pop(key, None)
        self._expiracoes.pop(key, None)

    def _existe_local(self, key: str) -> bool:
        self._purge(key)
        return key in self._strings or key in self._hashes or key in self._zsets

    async def exists(self, key: str) -> int:
        return 1 if self._existe_local(key) else 0

    async def set(
        self,
        key: str,
        value: str,
        *,
        nx: bool = False,
        ex: int | None = None,
    ) -> bool:
        if nx and self._existe_local(key):
            return False
        self._strings[key] = value
        if ex is not None:
            self._expiracoes[key] = time.time() + ex
        else:
            self._expiracoes.pop(key, None)
        return True

    async def get(self, key: str) -> str | None:
        self._purge(key)
        return self._strings.get(key)

    async def delete(self, *keys: str) -> int:
        removidos = 0
        for key in keys:
            self._purge(key)
            presente = key in self._strings or key in self._hashes or key in self._zsets
            self._strings.pop(key, None)
            self._hashes.pop(key, None)
            self._zsets.pop(key, None)
            self._expiracoes.pop(key, None)
            if presente:
                removidos += 1
        return removidos

    async def hset(self, key: str, *, mapping: dict[str, str]) -> int:
        self._purge(key)
        atual = self._hashes.setdefault(key, {})
        atual.update(mapping)
        return len(mapping)

    async def hgetall(self, key: str) -> dict[str, str]:
        self._purge(key)
        return dict(self._hashes.get(key, {}))

    async def zadd(self, key: str, mapping: dict[str, float]) -> int:
        self._purge(key)
        atual = self._zsets.setdefault(key, {})
        for membro, score in mapping.items():
            atual[membro] = float(score)
        return len(mapping)

    async def zrem(self, key: str, *membros: str) -> int:
        self._purge(key)
        atual = self._zsets.get(key, {})
        removidos = 0
        for membro in membros:
            if membro in atual:
                removidos += 1
                del atual[membro]
        if not atual and key in self._zsets:
            self._zsets.pop(key, None)
        return removidos

    async def zrange(self, key: str, inicio: int, fim: int) -> list[str]:
        self._purge(key)
        atual = self._zsets.get(key, {})
        ordenados = [m for m, _s in sorted(atual.items(), key=lambda item: (item[1], item[0]))]
        if not ordenados:
            return []
        if fim < 0:
            fim = len(ordenados) + fim
        return ordenados[inicio : fim + 1]


def test_n8n_rotas_401_sem_api_key() -> None:
    with TestClient(app) as client:
        r = client.post("/v1/interno/n8n/sms-pendentes/claim", json={"limite": 1})
    assert r.status_code == 401


def test_get_emails_pendentes_n8n_padroniza_payload() -> None:
    fake = _FakeRedis()
    app.dependency_overrides[interno_n8n._redis] = lambda: fake
    try:
        repo = RepositorioEmailsPendenteRedis()

        asyncio.run(
            repo.criar(
                fake,
                id_externo="email-1",
                destinatario="cliente@abc.com",
                tipo_template="APARECEU_BUSCA",
                contexto={"nome": "Cliente"},
                remetente="remetente-email",
                fornecedor_id="forn-1",
                cnpj_basico="12345678",
                origem="teste",
                consulta_id=None,
            ),
        )
        with TestClient(app) as client:
            r = client.get(
                "/v1/interno/n8n/emails-pendentes",
                headers={"Authorization": "Bearer test-api-key-unit"},
            )
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200
    corpo = r.json()
    assert corpo["total"] == 1
    item = corpo["itens"][0]
    assert item["canal"] == "email"
    assert item["destinatario"] == "cliente@abc.com"
    assert item["payload_envio"]["destinatario"] == "cliente@abc.com"
    assert item["payload_envio"]["tipo_template"] == "APARECEU_BUSCA"
    assert item["payload_envio"]["id_externo"] == "email-1"


def test_claim_sms_reserva_item_uma_unica_vez() -> None:
    fake = _FakeRedis()
    app.dependency_overrides[interno_n8n._redis] = lambda: fake
    try:
        repo = RepositorioSmsPendenteRedis()

        asyncio.run(
            repo.criar(
                fake,
                id_externo="sms-1",
                telefone="5511999999999",
                tipo_template="APARECEU_BUSCA",
                contexto={"nome": "Cliente"},
                remetente="abc",
                origem="teste",
                fornecedor_id="forn-1",
                cnpj_basico="12345678",
                consulta_id=None,
            ),
        )
        with TestClient(app) as client:
            r1 = client.post(
                "/v1/interno/n8n/sms-pendentes/claim",
                headers={"Authorization": "Bearer test-api-key-unit"},
                json={"limite": 1},
            )
            r2 = client.post(
                "/v1/interno/n8n/sms-pendentes/claim",
                headers={"Authorization": "Bearer test-api-key-unit"},
                json={"limite": 1},
            )
    finally:
        app.dependency_overrides.clear()

    assert r1.status_code == 200
    assert r1.json()["total"] == 1
    item = r1.json()["itens"][0]
    assert item["destinatario"] == "5511999999999"
    assert item["payload_envio"]["destinatario"] == "5511999999999"
    assert item["payload_envio"]["id_externo"] == "sms-1"

    assert r2.status_code == 200
    assert r2.json()["total"] == 0


def test_confirmar_consumo_sms_remove_eh_idempotente() -> None:
    fake = _FakeRedis()
    app.dependency_overrides[interno_n8n._redis] = lambda: fake
    try:
        repo = RepositorioSmsPendenteRedis()

        asyncio.run(
            repo.criar(
                fake,
                id_externo="sms-2",
                telefone="5511988888888",
                tipo_template="APARECEU_BUSCA",
                contexto={},
                remetente="abc",
                origem="teste",
                fornecedor_id=None,
                cnpj_basico=None,
                consulta_id=None,
            ),
        )
        with TestClient(app) as client:
            r1 = client.post(
                "/v1/interno/n8n/sms-pendentes/confirmar-consumo",
                headers={"Authorization": "Bearer test-api-key-unit"},
                json={"id_externo": "sms-2"},
            )
            r2 = client.post(
                "/v1/interno/n8n/sms-pendentes/confirmar-consumo",
                headers={"Authorization": "Bearer test-api-key-unit"},
                json={"id_externo": "sms-2"},
            )
    finally:
        app.dependency_overrides.clear()

    assert r1.status_code == 200
    assert r1.json()["status"] == "removido"
    assert r2.status_code == 200
    assert r2.json()["status"] == "ja_nao_existia"
