from enum import StrEnum


class Ambiente(StrEnum):
    """Runtime: máquina local vs implantação em produção (credenciais e políticas)."""

    LOCAL = "local"
    PRODUCAO = "producao"
