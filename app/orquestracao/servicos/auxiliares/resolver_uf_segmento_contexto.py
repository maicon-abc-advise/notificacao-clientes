from __future__ import annotations

import asyncpg

from app.orquestracao.api.dto.recebe_consulta_dto import RecebeConsultaCorpo
from app.orquestracao.externo.company_profile.extrair_uf import extrair_uf_de_company_profile
from app.orquestracao.repositorios.company_profile_repo import buscar_full_profile_por_cnpj_basico
from app.templates.contexto_genericos import SEGMENTO_GENERICO, UF_GENERICO


async def resolver_uf_e_segmento_para_contexto(
    pool: asyncpg.Pool,
    corpo: RecebeConsultaCorpo,
) -> tuple[str, str]:
    """Segmento: body ou genérico. UF: body, senão coluna ``uf`` ou JSON ``full_profile``, senão genérico."""
    seg = (corpo.segmento or "").strip() or SEGMENTO_GENERICO
    uf_body = (corpo.uf or "").strip()
    if uf_body:
        return uf_body, seg
    data, uf_col = await buscar_full_profile_por_cnpj_basico(pool, cnpj_basico=corpo.cnpj_basico)
    u = uf_col
    if not u and data:
        u = extrair_uf_de_company_profile(data)
    if u:
        return u, seg
    return UF_GENERICO, seg
