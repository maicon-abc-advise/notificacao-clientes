"""Normalização de telefone para WhatsApp (port de phone_utils.py legado)."""

from __future__ import annotations

import re

_WITH_COUNTRY_EXTRA_NINE = re.compile(r"^55\d{2}9\d{8,}$")


def _digits_only(phone: str) -> str:
    return re.sub(r"\D", "", phone.strip()).lstrip("0")


def _strip_extra_nine_after_ddd_with_country(digits: str) -> str:
    while len(digits) > 12 and _WITH_COUNTRY_EXTRA_NINE.match(digits):
        digits = digits[:4] + digits[5:]
    return digits


def _local_to_international(local: str) -> str:
    while len(local) > 10 and local[2] == "9":
        local = local[:2] + local[3:]
    if len(local) == 10:
        return f"55{local}"
    raise ValueError(f"Parte local inválida ({len(local)} dígitos): {local}")


def normalizar_telefone_whatsapp(phone: str) -> str:
    """Formato 12 dígitos: 55 + DDD + 8 (sem 9 extra após DDD)."""
    digits = _digits_only(phone)
    if not digits:
        raise ValueError("Telefone vazio")
    if digits.startswith(("0800", "3003", "4004")):
        raise ValueError(f"Número não suportado para WhatsApp: {phone}")
    if digits.startswith("55"):
        digits = _strip_extra_nine_after_ddd_with_country(digits)
    else:
        digits = _local_to_international(digits)
    if len(digits) != 12 or not digits.isdigit():
        raise ValueError(f"Telefone deve ter 12 dígitos (55+DDD+8): {phone}")
    return digits


def variantes_telefone_whatsapp(phone: str) -> tuple[str, str]:
    sem_nove = normalizar_telefone_whatsapp(phone)
    com_nove = sem_nove[:4] + "9" + sem_nove[4:]
    if len(com_nove) != 13:
        raise ValueError(f"Telefone com 9 inválido: {com_nove}")
    return sem_nove, com_nove
