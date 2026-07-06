"""Testes do backfill de variantes nos pendentes de e-mail."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

from app.dashboard.servicos.decidir_variantes_email_servico import decidir_variantes_email_pendentes
from app.orquestracao.repositorios.redis_emails_pendentes_repo import KEY_INDEX, chave_hash
from app.templates.modelo import CodigoTipoTemplate


class _RedisFake:
    def __init__(self) -> None:
        self._hashes: dict[str, dict[str, str]] = {}
        self._z: dict[str, float] = {}

    async def zrevrange(self, key: str, start: int, end: int) -> list[str]:
        assert key == KEY_INDEX
        ordenados = sorted(self._z.items(), key=lambda x: x[1], reverse=True)
        fatia = ordenados[start : end + 1 if end >= 0 else None]
        return [ext for ext, _ in fatia]

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self._hashes.get(key, {}))

    async def hset(self, key: str, *, mapping: dict[str, str]) -> None:
        self._hashes.setdefault(key, {}).update(mapping)

    async def zrem(self, key: str, member: str) -> None:
        self._z.pop(member, None)

    def seed_pendente(
        self,
        id_externo: str,
        *,
        tipo_template: str,
        cnpj_basico: str = "12345678",
        variante: str | None = None,
    ) -> None:
        key = chave_hash(id_externo)
        dados: dict[str, str] = {
            "id_externo": id_externo,
            "destinatario": "a@b.com",
            "tipo_template": tipo_template,
            "contexto_json": json.dumps({}),
            "cnpj_basico": cnpj_basico,
            "origem": "teste",
            "criado_em": "1",
        }
        if variante is not None:
            dados["variante"] = variante
        self._hashes[key] = dados
        self._z[id_externo] = float(id_externo.replace("ext", "") or 1)


def test_decidir_variantes_atualiza_sem_variante() -> None:
    redis = _RedisFake()
    redis.seed_pendente("ext1", tipo_template=CodigoTipoTemplate.APARECEU_BUSCA.value)

    with patch(
        "app.dashboard.servicos.decidir_variantes_email_servico.resolver_variante_email_busca",
        new=AsyncMock(return_value=("elaborado", "exp-test")),
    ):
        stats = asyncio.run(decidir_variantes_email_pendentes(redis))  # type: ignore[arg-type]

    assert stats == {
        "total_analisados": 1,
        "atualizados": 1,
        "sobrescritos": 0,
        "simples": 0,
        "elaborado": 1,
        "ignorados_tipo": 0,
        "erros": 0,
    }
    raw = asyncio.run(redis.hgetall(chave_hash("ext1")))
    assert raw["variante"] == "elaborado"
    assert raw["experimento_id"] == "exp-test"


def test_decidir_variantes_recalcula_quem_ja_tinha_e_ignora_tipo_nao_busca() -> None:
    redis = _RedisFake()
    redis.seed_pendente(
        "ext2",
        tipo_template=CodigoTipoTemplate.APARECEU_BUSCA.value,
        variante="simples",
    )
    redis.seed_pendente("ext3", tipo_template=CodigoTipoTemplate.CREDITOS_NO_FIM.value)

    with patch(
        "app.dashboard.servicos.decidir_variantes_email_servico.resolver_variante_email_busca",
        new=AsyncMock(return_value=("elaborado", "exp-test")),
    ) as mock_resolver:
        stats = asyncio.run(decidir_variantes_email_pendentes(redis))  # type: ignore[arg-type]

    mock_resolver.assert_called_once()
    assert stats["total_analisados"] == 2
    assert stats["atualizados"] == 1
    assert stats["sobrescritos"] == 1
    assert stats["ignorados_tipo"] == 1
    raw = asyncio.run(redis.hgetall(chave_hash("ext2")))
    assert raw["variante"] == "elaborado"
