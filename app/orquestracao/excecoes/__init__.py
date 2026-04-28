class ConsultaNaoEncontradaError(Exception):
    def __init__(self, id_consulta: str) -> None:
        super().__init__(f"consulta não encontrada: {id_consulta}")
        self.id_consulta = id_consulta


class ConsultaJaNotificadaError(Exception):
    """Já existe notificação em fila (e-mail pendente, SMS pendente ou e-mail aguardando confirmação) para esta consulta."""

    def __init__(self, id_consulta: str) -> None:
        super().__init__(
            f"já existe notificação ativa para esta consulta: {id_consulta}",
        )
        self.id_consulta = id_consulta
